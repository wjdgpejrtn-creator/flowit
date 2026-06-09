from __future__ import annotations

from uuid import UUID, uuid4

from common_schemas import Edge, NodeInstance, Position, WorkflowSchema

from ..value_objects.skeleton import (
    AssembledDraft,
    DraftEdge,
    DraftNode,
    ExtractedEntities,
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


class SkeletonAssembler:
    def __init__(self, extractor: SkeletonEntityExtractor | None = None) -> None:
        self._extractor = extractor or SkeletonEntityExtractor()

    # ── 선택 ────────────────────────────────────────────────────────────────
    def _select(self, entities: ExtractedEntities, text: str) -> Skeleton:
        """발화·엔티티로 스켈레톤을 결정적으로 고른다.

        규칙: ① 검증 루프 함의(needs_gate) → quality_loop(gate+generator 불변 보장).
        ② 아니면 intent 키워드 최다 매칭. ③ 무매칭이면 트리거 종류로 유추(이벤트성→
        event_response, 그 외→scheduled_pipeline = 최범용).
        """
        if entities.needs_gate:
            gate_skel = find_skeleton("quality_loop")
            if gate_skel is not None:
                return gate_skel

        best: tuple[int, int, Skeleton] | None = None
        for neg_idx, skel in enumerate(SKELETONS):
            score = sum(1 for kw in skel.intent_keywords if kw in text)
            # 동률이면 정의 순서가 앞선 것 우선(neg_idx 작을수록) → 결정적.
            cand = (score, -neg_idx, skel)
            if best is None or cand > best:
                best = cand
        if best is not None and best[0] > 0:
            return best[2]

        if entities.trigger in ("webhook_trigger", "event_trigger", "file_watch_trigger"):
            return find_skeleton("event_response") or SKELETONS[0]
        return find_skeleton("scheduled_pipeline") or SKELETONS[0]

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

    # ── 조립 ────────────────────────────────────────────────────────────────
    def assemble(self, utterance: str) -> AssembledDraft | None:
        """발화를 결정적 워크플로우 골격으로 조립. 조립할 재료가 없으면 None(LLM 폴백).

        None 반환 = 트리거 외 슬롯 재료(source/transform/sink/gate)가 전무 → 잡담이거나
        스켈레톤이 잡지 못하는 요청. composer는 이때 기존 LLM drafter 경로로 폴백한다.
        """
        text = utterance.lower()
        entities = self._extractor.extract(text)
        if entities.is_empty():
            return None
        skeleton = self._select(entities, text)
        return self._fill_and_wire(skeleton, entities)

    def _fill_and_wire(self, skeleton: Skeleton, entities: ExtractedEntities) -> AssembledDraft:
        warnings: list[str] = []
        by_role: dict[SlotRole, list[DraftNode]] = {}

        for slot in skeleton.slots:
            mats = [m for m in self._materials(slot.role, entities) if m in slot.candidates]
            if slot.cardinality == "one":
                mats = mats[:1]
            if not mats and slot.required:
                if slot.default_node_type:
                    mats = [slot.default_node_type]
                else:
                    warnings.append(f"required slot '{slot.role.value}' 미충전 (발화에서 추출 실패)")
                    continue
            nodes = [
                DraftNode(ref=f"{slot.role.value}_{i}", node_type=nt, role=slot.role)
                for i, nt in enumerate(mats)
            ]
            if nodes:
                by_role[slot.role] = nodes

        trigger = by_role.get(SlotRole.TRIGGER, [])
        sources = by_role.get(SlotRole.SOURCE, [])
        transforms = by_role.get(SlotRole.TRANSFORM, [])
        gate = by_role.get(SlotRole.GATE, [])
        sinks = by_role.get(SlotRole.SINK, [])

        all_nodes = trigger + sources + transforms + sinks + gate
        edges: list[DraftEdge] = []

        def chain(seq: list[DraftNode]) -> None:
            for a, b in zip(seq, seq[1:]):
                edges.append(DraftEdge(from_ref=a.ref, to_ref=b.ref))

        if gate and transforms:
            # 검증 루프: trigger→source→transform 선형, 마지막 transform↔gate back-edge,
            # gate 통과(true)→sink(있으면). quality_gate_loop 구조·엔진 계약 그대로.
            pre = trigger + sources + transforms
            chain(pre)
            gen = transforms[-1]
            evaluator = gate[0]
            edges.append(DraftEdge(from_ref=gen.ref, to_ref=evaluator.ref))
            edges.append(DraftEdge(from_ref=evaluator.ref, to_ref=gen.ref, from_handle="false"))
            if sinks:
                edges.append(DraftEdge(from_ref=evaluator.ref, to_ref=sinks[0].ref, from_handle="true"))
                chain(sinks)
        else:
            # 선형 파이프라인: trigger→source→transform→sink.
            if gate and not transforms:  # 방어 — 선택 규칙상 도달 불가(quality_loop가 transform 강제)
                warnings.append("gate 슬롯이 transform 없이 활성 — gate 무시")
                gate = []
                all_nodes = trigger + sources + transforms + sinks
            chain(trigger + sources + transforms + sinks)

        return AssembledDraft(
            skeleton_name=skeleton.name,
            nodes=tuple(all_nodes),
            edges=tuple(edges),
            warnings=tuple(warnings),
        )


def to_workflow_schema(
    draft: AssembledDraft,
    node_id_by_type: dict[str, UUID],
    owner_user_id: UUID,
    name: str | None = None,
) -> WorkflowSchema:
    """조립 골격을 WorkflowSchema로 변환 (ADR-0026 §6.6.3 step 4→5 경계, 순수).

    node_type → 카탈로그 node_id 해소 + ref → instance_id 매핑. 파라미터는 빈 dict(LLM이
    step 5에서 채움). 카탈로그에 없는 node_type은 그 노드와 의존 엣지를 드롭한다(drafter
    `_build` 동작과 동형 — 스켈레톤 후보는 전부 카탈로그라 정상 경로에선 미발생).
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

    return WorkflowSchema(
        workflow_id=uuid4(),
        name=name or f"{draft.skeleton_name} workflow",
        scope="private",
        is_draft=True,
        nodes=nodes,
        connections=connections,
        owner_user_id=owner_user_id,
    )
