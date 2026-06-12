from __future__ import annotations

from uuid import UUID, uuid4

from common_schemas import Edge, NodeInstance, Position, WorkflowSchema

from ..value_objects.skeleton import (
    AssembledDraft,
    DraftEdge,
    DraftNode,
    ExtractedEntities,
    ResolvedSlots,
    Skeleton,
    SlotRole,
)
from .skeleton_entity_extractor import SkeletonEntityExtractor
from .skeleton_library import SKELETONS, find_skeleton

# 결정적 스켈레톤 조립기 (ADR-0026 §6.6.3) — 코드가 구조를, LLM이 파라미터를.
#
# 발화 → 엔티티 추출 → 스켈레톤 선택 → 슬롯 결정적 채움 → 엣지 배선. soft 모티프 힌트(§6.1,
# 효과 0)와 의미검색 랭킹(도메인 노드 누락)에 의존하지 않는다. 산출 AssembledDraft는 순수
# node_type 구조이며, composer가 `to_workflow_schema`로 카탈로그 node_id를 해소해
# WorkflowSchema로 만들고 LLM이 파라미터만 채운다(step 5).

_GATE_DEFAULT = "if_condition"
# 콘텐츠(transform) 산출물이 갈 곳이 없을 때의 기본 출력 — "보고서 작성"처럼 출력 채널을
# 발화에서 안 준 경우 산출물을 문서로 떨군다(2026-06-09 측정: sink 없는 transform-종단을 qa가
# 불완전으로 저평가). 문서가 보고서/생성물의 자연스러운 기본 산출처(google_docs_write).
_DEFAULT_CONTENT_SINK = "google_docs_write"
# 명시 출력 채널(sink)만 있고 입력/가공 신호가 없을 때(예 "보고서 PDF로 만들어서 메일로") 콘텐츠를
# 생성할 기본 생산자. AI 노드가 발화 내용으로 산출물을 만들어 명시 sink들로 전달한다. _AI라 retriever
# core-LLM 후보에 항상 존재(#418) → scaffold 후보 보강도 무비용.
_DEFAULT_CONTENT_PRODUCER = "anthropic_chat"


class SkeletonAssembler:
    def __init__(self, extractor: SkeletonEntityExtractor | None = None) -> None:
        self._extractor = extractor or SkeletonEntityExtractor()

    @property
    def extractor(self) -> SkeletonEntityExtractor:
        """공유 엔티티 추출기(읽기 전용). 소비처(composer)가 명시 I/O 노드 보장 등에 재사용 —
        별도 인스턴스 생성으로 인한 룰 드리프트 방지."""
        return self._extractor

    # ── 선택 ────────────────────────────────────────────────────────────────
    def _select(self, entities: ExtractedEntities, text: str) -> Skeleton | None:
        """발화·엔티티로 선형 계열 스켈레톤을 결정적으로 고른다. 확신 없으면 None(LLM 폴백).

        규칙: ① 검증 루프 함의(needs_gate) → quality_loop. ② intent 키워드 최다 매칭(>0).
        ③ 이벤트/스케줄 트리거 명시 → event_response/scheduled_pipeline. ④ 그 외엔 **실제
        파이프라인(source 또는 transform 추출)일 때만** scheduled_pipeline, sink만 있거나 빈
        trivial이면 **None**(catch-all 강제 금지 — RC1). 근거: 무조건 scheduled_pipeline 폴백이
        분기·희소 발화를 선형으로 납작화해 if_condition/노드를 소실시켰다(skeleton-regressor-fix).
        """
        if entities.needs_gate:
            gate_skel = find_skeleton("quality_loop")
            if gate_skel is not None:
                return gate_skel

        # 선형 계열만 후보 — 분기/팬아웃(control 슬롯 보유)은 shape 라우팅이 전담하므로
        # 여기서 고르면 _assemble_linear가 router/splitter/merger를 무시해 구조가 깨진다.
        _CONTROL = {
            SlotRole.ROUTER, SlotRole.SPLITTER, SlotRole.MERGER,
            SlotRole.DELAY, SlotRole.TERMINAL,
        }
        linear_family = [
            s for s in SKELETONS if not any(sl.role in _CONTROL for sl in s.slots)
        ]
        best: tuple[int, int, Skeleton] | None = None
        for neg_idx, skel in enumerate(linear_family):
            score = sum(1 for kw in skel.intent_keywords if kw in text)
            # 동률이면 정의 순서가 앞선 것 우선(neg_idx 작을수록) → 결정적.
            cand = (score, -neg_idx, skel)
            if best is None or cand > best:
                best = cand
        if best is not None and best[0] > 0:
            return best[2]

        if entities.trigger in ("webhook_trigger", "event_trigger", "file_watch_trigger"):
            return find_skeleton("event_response") or SKELETONS[0]
        if entities.trigger == "schedule_trigger":
            return find_skeleton("scheduled_pipeline") or SKELETONS[0]
        # catch-all 제거(RC1): 실제 파이프라인 = 입력/가공(source|transform) **+ 출력(sink)** 둘 다
        # 있을 때만 scheduled_pipeline. 출력 채널 없는 transform-only는 _DEFAULT_CONTENT_SINK
        # (google_docs_write) 오주입으로 저품질이 됐다(측정: lin_fetch_summarize/branch_sentiment
        # qa≈4-6 < LLM 자유조립 10) → None(LLM 폴백). sink-only/trivial도 None(transform 드롭 토막).
        # (스케줄/이벤트 트리거가 명시된 경우는 위에서 이미 분기 — "주간 보고서 작성"처럼 출력
        # 미언급이어도 trigger 신호가 확실하면 default 문서 sink가 정당, #441.)
        if entities.sinks and (entities.sources or entities.transforms):
            return find_skeleton("scheduled_pipeline") or SKELETONS[0]
        return None

    # ── 슬롯 충전 재료 ────────────────────────────────────────────────────────
    @staticmethod
    def _materials(role: SlotRole, entities: ExtractedEntities) -> tuple[str, ...]:
        if role == SlotRole.TRIGGER:
            return (entities.trigger,) if entities.trigger else ()
        if role == SlotRole.SOURCE:
            return entities.sources
        if role == SlotRole.TRANSFORM:
            return entities.transforms
        if role == SlotRole.SINK:
            return entities.sinks
        if role == SlotRole.GATE:
            return (_GATE_DEFAULT,) if entities.needs_gate else ()
        return ()

    # 의미검색 그라운딩 대상 역할 — 사용자가 발화에 **명시하는 외부서비스 식별** 슬롯만.
    # transform/control(gate/router/…)은 제외: transform 후보(_AI)는 core LLM 노드라 retriever가
    # 항상 후보에 넣어(#418 _fetch_core_llm_candidates) 비변별적 → over-add. control 슬롯은
    # 코드가 default로 결정(사용자가 loop_list/if_condition을 발화 안 함).
    _GROUNDABLE_ROLES = frozenset({SlotRole.SOURCE, SlotRole.SINK})

    # ── 슬롯 채움 (공통) ──────────────────────────────────────────────────────
    def _collect(
        self,
        skeleton: Skeleton,
        entities: ExtractedEntities,
        grounding: tuple[str, ...] = (),
        resolved: ResolvedSlots | None = None,
    ) -> tuple[dict[SlotRole, list[DraftNode]], list[str]]:
        """스켈레톤 슬롯을 채운다. 우선순위: ① 앙상블(resolved) > ② 렉시컬 > ③ 그라운딩 > ④ default.

        반환: (역할→DraftNode 목록, 경고 목록). control 슬롯(router/splitter/merger)과
        scorer는 _materials가 () → required+default로 항상 채워진다(사용자가 loop_list나
        llm_judge를 발화하지 않으므로 구조 슬롯은 코드가 결정).

        앙상블(ADR-0026 §6.6 Phase 2): ``resolved``가 주어지면 SOURCE/SINK는 다중신호 가중투표
        (lexical+semantic+ontology+LLM)가 확정한 노드로 채운다 — 렉시컬은 앙상블의 한 voter라
        이미 반영(렉시컬 적중 노드는 weight 1.0이라 항상 임계 통과·보존). 앙상블이 그 역할에
        기권하면(빈 픽) 아래 렉시컬/그라운딩으로 폴백.

        그라운딩(#453, 레거시 폴백): 앙상블 미주입/기권 시 렉시컬이 비운 source/sink 슬롯을
        ``grounding``(BGE-M3 rank 순 후보)으로 메운다 — 어휘 갭을 손 사전 대신 retriever가 닫는다.
        ``resolved``/``grounding`` 모두 없으면 순수 렉시컬(기존 동작 — 단위테스트 호환).
        """
        warnings: list[str] = []
        by_role: dict[SlotRole, list[DraftNode]] = {}
        for slot in skeleton.slots:
            mats = [m for m in self._materials(slot.role, entities) if m in slot.candidates]
            if resolved is not None and resolved.has_pick(slot.role):
                ens = [nt for nt in resolved.for_role(slot.role) if nt in slot.candidates]
                if ens:
                    mats = ens
            if not mats and grounding and slot.role in self._GROUNDABLE_ROLES:
                mats = [t for t in grounding if t in slot.candidates][:1]
            if slot.cardinality == "one":
                mats = mats[:1]
            if not mats and slot.required:
                if slot.default_node_type:
                    mats = [slot.default_node_type]
                else:
                    warnings.append(f"required slot '{slot.role.value}' 미충전 (발화에서 추출 실패)")
                    continue
            if mats:
                by_role[slot.role] = [
                    DraftNode(ref=f"{slot.role.value}_{i}", node_type=nt, role=slot.role)
                    for i, nt in enumerate(mats)
                ]
        return by_role, warnings

    @staticmethod
    def _chain(edges: list[DraftEdge], seq: list[DraftNode]) -> None:
        for a, b in zip(seq, seq[1:]):
            edges.append(DraftEdge(from_ref=a.ref, to_ref=b.ref))

    # ── 조립 (shape 라우팅) ───────────────────────────────────────────────────
    def assemble(
        self,
        utterance: str,
        candidate_node_types: list[str] | None = None,
        resolved_slots: ResolvedSlots | None = None,
    ) -> AssembledDraft | None:
        """발화를 결정적 워크플로우 골격으로 조립. 확신이 없으면 None(LLM drafter 폴백).

        스켈레톤은 "전부 처리"가 아니라 "확신할 때만 처리하는 fast-path"다(ADR-0026 §6.6).
        shape 신호로 분기/팬아웃 전용 조립으로 라우팅하고, 표현 못 하는 경우(중첩 조합,
        불완전 커버리지, 잡담)는 None을 반환해 composer가 기존 LLM drafter로 폴백하게 한다 —
        억지로 끼워맞춰 confident-wrong 워크플로우를 내는 것보다 낫다.

        ``resolved_slots``(선택, ADR-0026 §6.6 Phase 2): 앙상블(EnsembleSlotResolver)이 SOURCE/SINK
        를 다중신호 가중투표로 확정한 결과. 주어지면 lexical보다 우선해 슬롯을 채운다(`_collect`)
        — 발화 어휘 변형에 강건한 의미 기반 노드 선택. shape 라우팅은 여전히 렉시컬 신호 기준.

        ``candidate_node_types``(선택): retriever가 의미매칭한 후보 node_type을 **relevance rank
        순**으로 받는다. 렉시컬·앙상블이 비운 source/sink 슬롯을 이 후보로 그라운딩(#453, 레거시
        폴백). 둘 다 None이면 순수 렉시컬(기존 동작 — 단위테스트 호환).

        ⚠️ 중첩 합성(팬아웃 안 분기 등)은 현재 flat 라이브러리로 결정적 표현 불가 → LLM bail.
        실측상 흔하면 모티프 연산자 합성으로 진화(§6.6 로드맵, 측정 게이트).
        """
        text = utterance.lower()
        entities = self._extractor.extract(text)
        if entities.is_empty():
            return None
        grounding = tuple(candidate_node_types or ())
        resolved = resolved_slots

        # shape 라우팅. approval은 "승인되면…아니면" 구조라 branch 신호를 동반하므로 branch를
        # 포섭(approval 우선). guard("넘으면")는 branch("아니면")·approval("승인")이 동반되면
        # 그쪽이 더 구체적이므로 양보(명시 2-way 분기/승인 우선). 그 외 서로 다른 shape가 2개
        # 이상이면 중첩 합성 → flat 표현 불가 → LLM bail(억지 끼워맞춤 방지, §6.6 측정 게이트).
        shapes = entities.shape_signals()
        if "approval" in shapes:
            shapes.discard("branch")
            shapes.discard("guard")
        if "branch" in shapes:
            shapes.discard("guard")
        if len(shapes) >= 2:
            return None
        if "approval" in shapes:
            return self._assemble_approval(entities, grounding, resolved)
        if "retry" in shapes:
            return self._assemble_retry(entities, grounding, resolved)
        if "fanout" in shapes:
            return self._assemble_fanout(entities, grounding, resolved)
        if "branch" in shapes:
            return self._assemble_branch(entities, grounding, resolved)
        if "guard" in shapes:
            return self._assemble_conditional(entities, grounding, resolved)

        # 콘텐츠 전달(sink-anchored): 출력 채널(sink)을 **둘 이상** 명시했는데 트리거/소스/가공
        # 신호가 전혀 없는 발화("보고서 PDF로 만들어서 메일로 보내줘"). _select는 이를 RC1
        # (catch-all 금지) 규칙으로 bail → LLM 자유 draft가 명시 sink(pdf_generate)를 드롭하던
        # 회귀(#502 측정: pdf_generate는 BGE-M3 #2 후보였는데 Gemma가 미선택). 생성형 콘텐츠를
        # 복수 채널로 전달하는 구조는 결정적이므로(생산자→sink 팬) 코드가 직접 조립한다.
        # RC1과 구분: 단일 sink/trivial은 채널 모호·과조립 위험이라 여전히 LLM 폴백(여기 미해당).
        if (
            not entities.trigger
            and not entities.sources
            and not entities.transforms
            and len(entities.sinks) >= 2
        ):
            return self._assemble_content_delivery(entities)

        skeleton = self._select(entities, text)
        if skeleton is None:
            return None  # 확신 가는 선형 매칭 없음 — LLM 폴백(catch-all 강제 금지, RC1)
        draft = self._assemble_linear(skeleton, entities, grounding, resolved)
        if any("미충전" in w for w in draft.warnings):
            return None  # 불완전 커버리지(출력 채널 등) — LLM 폴백
        return draft

    # ── 선형 / 검증 루프 ──────────────────────────────────────────────────────
    def _assemble_linear(
        self, skeleton: Skeleton, entities: ExtractedEntities, grounding: tuple[str, ...] = (),
        resolved: ResolvedSlots | None = None,
    ) -> AssembledDraft:
        by_role, warnings = self._collect(skeleton, entities, grounding, resolved)
        trigger = by_role.get(SlotRole.TRIGGER, [])
        sources = by_role.get(SlotRole.SOURCE, [])
        transforms = by_role.get(SlotRole.TRANSFORM, [])
        scorer = by_role.get(SlotRole.SCORER, [])
        gate = by_role.get(SlotRole.GATE, [])
        sinks = by_role.get(SlotRole.SINK, [])

        # 콘텐츠 생산(transform)이 있는데 출력 채널이 없으면 기본 문서 출력 부여 — 산출물이 갈 곳
        # 없는 워크플로우를 qa가 불완전으로 저평가하는 것 방지. 순수 선형(gate 없음)에만 적용:
        # quality_loop(gate)는 점수갭(#438)이 본질이라 무관. source-only(transform 없음)는 종단 유지.
        if transforms and not sinks and not gate:
            sinks = [DraftNode(ref="sink_0", node_type=_DEFAULT_CONTENT_SINK, role=SlotRole.SINK)]

        all_nodes = trigger + sources + transforms + scorer + sinks + gate
        edges: list[DraftEdge] = []

        def fan_sinks(source_ref: str, handle: str = "output") -> None:
            # 복수 sink는 직렬(sink→sink)이 아니라 마지막 처리 노드에서 **병렬 분기**.
            for s in sinks:
                edges.append(DraftEdge(from_ref=source_ref, to_ref=s.ref, from_handle=handle))

        if gate and transforms:
            # 검증 루프: spine 선형 → scorer(점수화) → gate, gate→generator back-edge(재생성),
            # gate 통과(true)→sink 분기. scorer가 score를 내고 gate가 그 점수를 gte 비교한다
            # (#438 §6.6). back-edge는 scorer가 아니라 generator로 — 재생성 후 다시 채점 루프.
            spine = trigger + sources + transforms
            self._chain(edges, spine)
            gen, evaluator = transforms[-1], gate[0]
            if scorer:
                judge = scorer[0]
                edges.append(DraftEdge(from_ref=gen.ref, to_ref=judge.ref))
                edges.append(DraftEdge(from_ref=judge.ref, to_ref=evaluator.ref))
            else:  # 방어 — scorer 슬롯 없는 스켈레톤(현재 quality_loop만 보유)
                edges.append(DraftEdge(from_ref=gen.ref, to_ref=evaluator.ref))
            edges.append(DraftEdge(from_ref=evaluator.ref, to_ref=gen.ref, from_handle="false"))
            fan_sinks(evaluator.ref, handle="true")
        else:
            if gate and not transforms:  # 방어 — 선택 규칙상 도달 불가
                warnings.append("gate 슬롯이 transform 없이 활성 — gate 무시")
                all_nodes = trigger + sources + transforms + sinks
            spine = trigger + sources + transforms
            self._chain(edges, spine)
            if spine:
                fan_sinks(spine[-1].ref)
            else:
                self._chain(edges, sinks)  # spine 전무 — 방어적 직렬

        return AssembledDraft(
            skeleton_name=skeleton.name, nodes=tuple(all_nodes),
            edges=tuple(edges), warnings=tuple(warnings),
        )

    # ── 콘텐츠 전달 (sink-anchored, 생산자 자동) ───────────────────────────────
    def _assemble_content_delivery(self, entities: ExtractedEntities) -> AssembledDraft:
        """생산자(ai)→명시 sink 팬. 트리거/소스/가공 없이 출력 채널만 ≥2개 명시된 발화 전용.

        "보고서를 PDF로 만들어서 메일로 보내줘" → anthropic_chat(콘텐츠 생성) → {pdf_generate,
        email_send} 병렬 분기. 복수 sink는 기존 컨벤션(`fan_sinks`)대로 직렬이 아니라 마지막
        생산 노드에서 병렬 분기한다. 구조는 결정적이고 LLM은 파라미터만 채운다(scaffold 경로).

        sink는 발화에서 직접 명시된 출력 채널(lexical sink 추출)이라 의미 디스앰비규에이션이
        불필요 → 앙상블/그라운딩 미적용(어휘 변형으로 추출 실패 시 sink<2 → 이 경로 미진입,
        LLM 폴백). 생산자는 _AI 기본 노드라 retriever core-LLM 후보에 항상 존재.
        """
        producer = DraftNode(
            ref="transform_0", node_type=_DEFAULT_CONTENT_PRODUCER, role=SlotRole.TRANSFORM
        )
        sinks = [
            DraftNode(ref=f"sink_{i}", node_type=nt, role=SlotRole.SINK)
            for i, nt in enumerate(entities.sinks)
        ]
        edges = [DraftEdge(from_ref=producer.ref, to_ref=s.ref) for s in sinks]
        return AssembledDraft(
            skeleton_name="content_delivery",
            nodes=tuple([producer, *sinks]),
            edges=tuple(edges),
            warnings=(),
        )

    # ── 분기 (XOR) ────────────────────────────────────────────────────────────
    def _assemble_branch(
        self, entities: ExtractedEntities, grounding: tuple[str, ...] = (),
        resolved: ResolvedSlots | None = None,
    ) -> AssembledDraft | None:
        """branch_on_classification — classifier(ai)→router(if_condition)→2갈래 sink.

        MVP=2-way(if_condition true/false). sink가 정확히 2개일 때만 결정적 조립(3갈래↑는
        switch_case 다중 라우팅이 정적으로 모호 → LLM bail). 핸들은 BranchEvaluator의
        if_condition.branch selector(true/false)와 정합. sink는 2갈래 분기의 타깃이라 발화에
        명시돼야 하므로 렉시컬 sink 수(2)로 게이트한다(그라운딩 top-1로 토막내지 않도록 게이트는
        그라운딩 전 entities.sinks 기준 — 분기는 채널 식별이 본질).
        """
        if len(entities.sinks) != 2:
            return None
        skeleton = find_skeleton("branch_on_classification")
        if skeleton is None:
            return None
        by_role, warnings = self._collect(skeleton, entities, grounding, resolved)
        if warnings:  # required 미충전(이론상 sink뿐이나 방어)
            return None
        trigger = by_role[SlotRole.TRIGGER]
        sources = by_role.get(SlotRole.SOURCE, [])
        classifier = by_role[SlotRole.TRANSFORM]
        router = by_role[SlotRole.ROUTER]
        sinks = by_role[SlotRole.SINK]

        edges: list[DraftEdge] = []
        spine = trigger + sources + classifier
        self._chain(edges, spine)
        edges.append(DraftEdge(from_ref=classifier[-1].ref, to_ref=router[0].ref))
        edges.append(DraftEdge(from_ref=router[0].ref, to_ref=sinks[0].ref, from_handle="true"))
        edges.append(DraftEdge(from_ref=router[0].ref, to_ref=sinks[1].ref, from_handle="false"))

        return AssembledDraft(
            skeleton_name=skeleton.name,
            nodes=tuple(trigger + sources + classifier + router + sinks),
            edges=tuple(edges), warnings=(),
        )

    # ── 단일 가드 조건문 ──────────────────────────────────────────────────────
    def _assemble_conditional(
        self, entities: ExtractedEntities, grounding: tuple[str, ...] = (),
        resolved: ResolvedSlots | None = None,
    ) -> AssembledDraft | None:
        """conditional_action — (transform?)→router(if_condition)→[true]→sink /[false]→terminal.

        "임계치 넘으면 경보" 류 단일 가드. transform optional(가드는 분류기 불필요 — if_condition이
        입력 직접 평가). action 채널(sink)을 발화에서 못 채우면 LLM bail. false→stop_workflow 자동
        부착으로 router outgoing=2 → motif(branch_on_classification) 통과. approval_gate와 동형이나
        transform이 optional이고 발동이 임계/비교 가드 어휘다.
        """
        if not entities.sinks:
            return None
        skeleton = find_skeleton("conditional_action")
        if skeleton is None:
            return None
        by_role, warnings = self._collect(skeleton, entities, grounding, resolved)
        if warnings:  # required(router/terminal/sink) 미충전 — 이론상 sink뿐이나 방어
            return None
        trigger = by_role[SlotRole.TRIGGER]
        sources = by_role.get(SlotRole.SOURCE, [])
        transform = by_role.get(SlotRole.TRANSFORM, [])  # optional — 분류기 동반 시만
        router = by_role[SlotRole.ROUTER]
        terminal = by_role[SlotRole.TERMINAL]
        sinks = by_role[SlotRole.SINK]

        edges: list[DraftEdge] = []
        spine = trigger + sources + transform
        self._chain(edges, spine)
        edges.append(DraftEdge(from_ref=spine[-1].ref, to_ref=router[0].ref))
        # 가드 미충족(false) → 종료 / 충족(true) → action sink 병렬 분기
        edges.append(DraftEdge(from_ref=router[0].ref, to_ref=terminal[0].ref, from_handle="false"))
        for s in sinks:
            edges.append(DraftEdge(from_ref=router[0].ref, to_ref=s.ref, from_handle="true"))

        return AssembledDraft(
            skeleton_name=skeleton.name,
            nodes=tuple(trigger + sources + transform + router + sinks + terminal),
            edges=tuple(edges), warnings=(),
        )

    # ── 팬아웃 (병렬 map) ─────────────────────────────────────────────────────
    def _assemble_fanout(
        self, entities: ExtractedEntities, grounding: tuple[str, ...] = (),
        resolved: ResolvedSlots | None = None,
    ) -> AssembledDraft | None:
        """fan_out_map — splitter(loop_list)→worker(ai)→merger(merge_branch)→sink.

        출력 채널(sink)을 발화에서 못 채우면 토막 골격 대신 LLM bail. loop_list/merge_branch
        출력은 list/int라 selector 없음 → 엣지 전부 live(BranchEvaluator degrade), 순수 DAG.
        """
        if not entities.sinks:
            return None
        skeleton = find_skeleton("fan_out_map")
        if skeleton is None:
            return None
        by_role, warnings = self._collect(skeleton, entities, grounding, resolved)
        if warnings:
            return None
        trigger = by_role[SlotRole.TRIGGER]
        sources = by_role.get(SlotRole.SOURCE, [])
        splitter = by_role[SlotRole.SPLITTER]
        worker = by_role[SlotRole.TRANSFORM]
        merger = by_role[SlotRole.MERGER]
        sinks = by_role[SlotRole.SINK]

        edges: list[DraftEdge] = []
        self._chain(edges, trigger + sources + splitter + worker + merger)
        for s in sinks:  # merger → sink 병렬 분기
            edges.append(DraftEdge(from_ref=merger[0].ref, to_ref=s.ref))

        return AssembledDraft(
            skeleton_name=skeleton.name,
            nodes=tuple(trigger + sources + splitter + worker + merger + sinks),
            edges=tuple(edges), warnings=(),
        )

    # ── 재시도 (백오프 루프) ──────────────────────────────────────────────────
    def _assemble_retry(
        self, entities: ExtractedEntities, grounding: tuple[str, ...] = (),
        resolved: ResolvedSlots | None = None,
    ) -> AssembledDraft | None:
        """retry_backoff — worker(실패 가능 연산)→gate(if_condition)→[false]→delay→worker 루프.

        재시도 대상(worker)=마지막 source/transform(외부 호출이 통상). 재시도할 연산이 없으면
        LLM bail. SCC={worker,gate,delay}에 condition(gate) 포함 → CyclicScheduler 수용.
        """
        skeleton = find_skeleton("retry_backoff")
        if skeleton is None:
            return None
        by_role, _ = self._collect(skeleton, entities, grounding, resolved)
        trigger = by_role[SlotRole.TRIGGER]
        sources = by_role.get(SlotRole.SOURCE, [])
        transforms = by_role.get(SlotRole.TRANSFORM, [])
        ops = sources + transforms
        if not ops:
            return None  # 재시도할 연산이 발화에 없음 → LLM
        gate = by_role[SlotRole.GATE]
        delay = by_role[SlotRole.DELAY]
        sinks = by_role.get(SlotRole.SINK, [])

        worker = ops[-1]
        edges: list[DraftEdge] = []
        self._chain(edges, trigger + ops)              # 진입 선형 (… → worker)
        edges.append(DraftEdge(from_ref=worker.ref, to_ref=gate[0].ref))
        # 실패(false) → delay 백오프 → worker 재시도 (back-edge)
        edges.append(DraftEdge(from_ref=gate[0].ref, to_ref=delay[0].ref, from_handle="false"))
        edges.append(DraftEdge(from_ref=delay[0].ref, to_ref=worker.ref))
        # 성공(true) → sink 병렬 분기
        for s in sinks:
            edges.append(DraftEdge(from_ref=gate[0].ref, to_ref=s.ref, from_handle="true"))

        return AssembledDraft(
            skeleton_name=skeleton.name,
            nodes=tuple(trigger + ops + gate + delay + sinks),
            edges=tuple(edges), warnings=(),
        )

    # ── 승인 게이트 (HITL) ────────────────────────────────────────────────────
    def _assemble_approval(
        self, entities: ExtractedEntities, grounding: tuple[str, ...] = (),
        resolved: ResolvedSlots | None = None,
    ) -> AssembledDraft | None:
        """approval_gate — proposer(ai)→router(if_condition)→[true]→sink /[false]→terminal.

        분기의 특수화(반려 갈래가 stop_workflow로 종료) — 루프 아님(DAG). 진행 채널(sink)을
        발화에서 못 채우면 LLM bail.
        """
        if not entities.sinks:
            return None
        skeleton = find_skeleton("approval_gate")
        if skeleton is None:
            return None
        by_role, warnings = self._collect(skeleton, entities, grounding, resolved)
        if warnings:
            return None
        trigger = by_role[SlotRole.TRIGGER]
        sources = by_role.get(SlotRole.SOURCE, [])
        proposer = by_role[SlotRole.TRANSFORM]
        router = by_role[SlotRole.ROUTER]
        terminal = by_role[SlotRole.TERMINAL]
        sinks = by_role[SlotRole.SINK]

        edges: list[DraftEdge] = []
        self._chain(edges, trigger + sources + proposer)
        edges.append(DraftEdge(from_ref=proposer[-1].ref, to_ref=router[0].ref))
        edges.append(DraftEdge(from_ref=router[0].ref, to_ref=terminal[0].ref, from_handle="false"))
        for s in sinks:  # 승인(true) → 진행 채널 병렬 분기
            edges.append(DraftEdge(from_ref=router[0].ref, to_ref=s.ref, from_handle="true"))

        return AssembledDraft(
            skeleton_name=skeleton.name,
            nodes=tuple(trigger + sources + proposer + router + terminal + sinks),
            edges=tuple(edges), warnings=(),
        )


def build_workflow_with_refs(
    draft: AssembledDraft,
    node_id_by_type: dict[str, UUID],
    owner_user_id: UUID,
    name: str | None = None,
) -> tuple[WorkflowSchema, dict[str, UUID]]:
    """조립 골격을 WorkflowSchema로 변환하고 ref→instance_id 맵을 함께 반환.

    구조(노드/엣지)는 코드가 결정적으로 빌드(LLM 무관). 파라미터는 빈 dict — composer가 ref
    맵으로 LLM 파라미터 채움 결과를 인스턴스에 적용한다(ADR-0026 §6.6.3 step5, 구조는 불변).
    카탈로그에 없는 node_type은 그 노드와 의존 엣지를 드롭한다(drafter `_build`와 동형 —
    스켈레톤 후보는 전부 카탈로그라 정상 경로에선 미발생).
    """
    instance_by_ref: dict[str, UUID] = {}
    nodes: list[NodeInstance] = []
    for i, dn in enumerate(draft.nodes):
        node_id = node_id_by_type.get(dn.node_type)
        if node_id is None:
            continue
        instance_id = uuid4()
        instance_by_ref[dn.ref] = instance_id
        nodes.append(
            NodeInstance(
                instance_id=instance_id,
                node_id=node_id,
                parameters={},
                position=Position(x=float(i * 220), y=0.0),
            )
        )

    connections: list[Edge] = []
    for de in draft.edges:
        from_id = instance_by_ref.get(de.from_ref)
        to_id = instance_by_ref.get(de.to_ref)
        if from_id is None or to_id is None:
            continue
        connections.append(
            Edge(
                from_instance_id=from_id,
                to_instance_id=to_id,
                from_handle=de.from_handle,
                to_handle=de.to_handle,
            )
        )

    wf = WorkflowSchema(
        workflow_id=uuid4(),
        name=name or f"{draft.skeleton_name} workflow",
        scope="private",
        is_draft=True,
        nodes=nodes,
        connections=connections,
        owner_user_id=owner_user_id,
    )
    return wf, instance_by_ref


def to_workflow_schema(
    draft: AssembledDraft,
    node_id_by_type: dict[str, UUID],
    owner_user_id: UUID,
    name: str | None = None,
) -> WorkflowSchema:
    """``build_workflow_with_refs``의 WorkflowSchema만 필요할 때의 얇은 래퍼 (ref 맵 무시)."""
    wf, _ = build_workflow_with_refs(draft, node_id_by_type, owner_user_id, name)
    return wf
