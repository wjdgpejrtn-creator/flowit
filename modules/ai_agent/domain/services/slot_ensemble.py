from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..ports.slot_mapper_port import SlotMapperPort
from ..value_objects.skeleton import ResolvedSlots, SlotRole
from .skeleton_entity_extractor import SkeletonEntityExtractor, suppressed_sink_variants
from .skeleton_library import ROLE_CANDIDATE_POOLS
from .slot_voters import SlotVoter, VoteContext

# 앙상블 슬롯 채움 resolver (ADR-0026 §6.6 Phase 2 — 노드 선택 의미화).
#
# 여러 독립 voter(lexical 정밀 + semantic BGE-M3 랭킹 + ontology 구조친화 + LLM 방향성)가
# 후보별로 투표하고, 가중합 ≥ 임계인 후보만 relevance 순으로 슬롯에 채운다. 합의할수록
# 확신↑ — "더 확실한 것이 선택된다". 아무도 임계를 못 넘기면 그 역할은 **기권**(빈 픽)해
# 조립기가 렉시컬/그라운딩/default로 폴백. 어휘 갭을 손 사전 대신 의미신호가 닫는다(§6.6.4).
#
# 적용 역할 = SOURCE/SINK만(외부서비스 식별). TRANSFORM/TRIGGER 제외 — transform 후보(_AI)는
# core LLM 노드라 retriever가 항상 상위에 올려(#418) 의미신호가 비변별적이고, trigger 어휘
# ("매주"/"웹훅")는 안정적이라 렉시컬+default로 충분(조립기 기존 처리 유지). 이는 기존
# `_GROUNDABLE_ROLES`(SOURCE/SINK) 결정과 동일 근거.
#
# LLM voter는 async라 싼 voter(sync)와 분리 — 싼 voter가 확신 못 한 역할만 1콜로 지연
# escalation(레이턴시 절약). llm_mapper 미주입이면 싼 voter만으로 동작(graceful degrade).

@dataclass(frozen=True)
class SlotDecision:
    """역할별 앙상블 결정 트레이스 (opt-in 텔레메트리 — 성능지표 수집용).

    어느 voter가 1순위 픽을 캐리했는지(``contributors``), LLM escalation이 떴는지
    (``escalated``), 확신 마진(``top_score``/``margin``)을 기록한다. 프로덕션은 trace 미요청
    시 미생성(무부하). 집계하면 escalation율·voter 귀속 분포·기권율·마진 분포가 나온다.
    """

    role: SlotRole
    picks: tuple[str, ...]                 # 최종 바인딩 node_type(기권 시 빈 튜플)
    escalated: bool                        # 이 역할에 LLM voter가 개입했나
    contributors: tuple[str, ...]          # 1순위 픽에 점수>0 기여한 voter 이름(escalation 시 "llm" 포함)
    top_score: float                       # 최고 가중합
    margin: float                          # 최고 − 차순위(확신도)


# 앙상블이 의미신호로 채우는 역할 — 나머지(transform/trigger/control)는 조립기 기존 경로.
_RESOLVE_ROLES: tuple[SlotRole, ...] = (SlotRole.SOURCE, SlotRole.SINK)

# 후보가 슬롯에 바인딩되는 가중합 절대 하한. semantic 1등 단독(weight 0.6)은 넘고,
# ontology 멤버십 단독(weight 0.25)은 못 넘게 — 약신호 단독 바인딩 방지. 골든셋 튜닝 대상.
_BIND_THRESHOLD = 0.5
# 다중 픽(many 슬롯) 상대 게이트 — 픽은 floor 통과 + **최고점의 이 비율 이상**이어야 채택.
# "더 확실한 것이 선택된다": 약한 2순위(예 ontology 멤버십에 업힌 차순위 source)가 floor만
# 겨우 넘어 끼어드는 over-add를 막고, 진짜 동급(둘 다 렉시컬 적중한 복수 sink)만 공존시킨다.
_TOP_RATIO = 0.7
# LLM voter(escalation) 가중치 — 강신호.
_LLM_WEIGHT = 1.0


class EnsembleSlotResolver:
    """싼 voter 가중투표 + (필요 시) LLM escalation으로 역할별 노드를 확정한다."""

    def __init__(
        self,
        voters: list[SlotVoter],
        llm_mapper: SlotMapperPort | None = None,
        *,
        extractor: SkeletonEntityExtractor | None = None,
        resolve_roles: tuple[SlotRole, ...] = _RESOLVE_ROLES,
        bind_threshold: float = _BIND_THRESHOLD,
        top_ratio: float = _TOP_RATIO,
        llm_weight: float = _LLM_WEIGHT,
    ) -> None:
        self._voters = voters
        self._llm_mapper = llm_mapper
        self._extractor = extractor or SkeletonEntityExtractor()
        self._roles = resolve_roles
        self._threshold = bind_threshold
        self._top_ratio = top_ratio
        self._llm_weight = llm_weight

    async def resolve(
        self,
        utterance: str,
        ranked_candidates: tuple[str, ...] = (),
        ontology_allowed: frozenset[str] = frozenset(),
        trace: list[SlotDecision] | None = None,
    ) -> ResolvedSlots:
        """발화 + 리트리버 랭킹(+온톨로지 허용집합)으로 역할별 앙상블 픽을 계산한다.

        싼 voter(lexical/semantic/ontology)로 먼저 풀고, 기권한 역할만 LLM으로 escalate.
        렉시컬 추출은 내부에서 1회 수행(조립기와 동일 발화라 결과 동일). ``trace``(opt-in sink)를
        주면 역할별 SlotDecision을 append한다(성능지표 수집 — 프로덕션 미요청 시 무부하).
        """
        ctx = VoteContext(
            utterance=utterance,
            entities=self._extractor.extract(utterance.lower()),
            ranked_candidates=tuple(ranked_candidates),
            ontology_allowed=frozenset(ontology_allowed),
        )
        return await self._resolve_ctx(ctx, trace=trace)

    async def _resolve_ctx(
        self, ctx: VoteContext, trace: list[SlotDecision] | None = None
    ) -> ResolvedSlots:
        by_role: dict[SlotRole, tuple[str, ...]] = {}
        uncertain: dict[SlotRole, tuple[str, ...]] = {}
        # 역할 → (scores, breakdown, picks, escalated) — trace 생성용 최종 상태 보존.
        state: dict[SlotRole, tuple[dict[str, float], dict[str, dict[str, float]], tuple[str, ...], bool]] = {}

        for role in self._roles:
            pool = ROLE_CANDIDATE_POOLS.get(role, ())
            if not pool:
                continue
            # 방향성 소스-블리드 차단(semantic 표까지): read-service가 source로 잡혔는데 그
            # 서비스 write의 send-cue가 없으면 SINK 풀에서 그 write를 제거(렉시컬과 동일 규칙
            # 공유). SOURCE를 먼저 풀어 by_role에 있으므로 SINK 시점에 참조 가능.
            if role == SlotRole.SINK:
                drop = suppressed_sink_variants(
                    ctx.utterance.lower(), by_role.get(SlotRole.SOURCE, ())
                )
                if drop:
                    pool = tuple(nt for nt in pool if nt not in drop)
            scores, breakdown = self._combine(ctx, role, pool)
            picks = self._select(scores)
            state[role] = (scores, breakdown, picks, False)
            if picks:
                by_role[role] = picks
            else:
                uncertain[role] = pool

        # 지연 escalation — 싼 voter가 확신 못 한 역할만 LLM 1콜로 재시도.
        if uncertain and self._llm_mapper is not None:
            llm = await self._llm_mapper.map_slots(ctx.utterance, uncertain)
            for role, pool in uncertain.items():
                extra = {nt: conf for nt, conf in llm.get(role, ()) if nt in set(pool)}
                scores, breakdown = self._combine(ctx, role, pool, extra=extra)
                picks = self._select(scores)
                state[role] = (scores, breakdown, picks, True)
                if picks:
                    by_role[role] = picks

        if trace is not None:
            for role in self._roles:
                if role in state:
                    trace.append(self._decision(role, *state[role]))

        return ResolvedSlots(by_role=by_role)

    def _combine(
        self,
        ctx: VoteContext,
        role: SlotRole,
        pool: tuple[str, ...],
        extra: dict[str, float] | None = None,
    ) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
        """voter별 점수를 가중합 + per-voter 기여 breakdown. ``extra``(LLM)는 "llm"으로 가산."""
        scores: dict[str, float] = defaultdict(float)
        breakdown: dict[str, dict[str, float]] = defaultdict(dict)
        for voter in self._voters:
            for nt, s in voter.vote(ctx, role, pool).items():
                contrib = voter.weight * s
                scores[nt] += contrib
                breakdown[nt][voter.name] = breakdown[nt].get(voter.name, 0.0) + contrib
        if extra:
            for nt, conf in extra.items():
                contrib = self._llm_weight * conf
                scores[nt] += contrib
                breakdown[nt]["llm"] = breakdown[nt].get("llm", 0.0) + contrib
        return dict(scores), {k: dict(v) for k, v in breakdown.items()}

    @staticmethod
    def _decision(
        role: SlotRole,
        scores: dict[str, float],
        breakdown: dict[str, dict[str, float]],
        picks: tuple[str, ...],
        escalated: bool,
    ) -> SlotDecision:
        """1순위 픽 기여 voter + 마진으로 SlotDecision 구성(기권이면 빈 픽)."""
        if not picks:
            return SlotDecision(role, (), escalated, (), 0.0, 0.0)
        top = picks[0]
        contributors = tuple(sorted(v for v, c in breakdown.get(top, {}).items() if c > 0))
        ordered = sorted(scores.values(), reverse=True)
        top_score = ordered[0]
        second = ordered[1] if len(ordered) > 1 else 0.0
        return SlotDecision(role, picks, escalated, contributors, top_score, top_score - second)

    def _select(self, scores: dict[str, float]) -> tuple[str, ...]:
        """floor 통과 + 최고점의 top_ratio 이상 후보를 점수 내림차순(동점은 node_type 사전순)으로.

        floor는 약신호 단독 바인딩을 막고, top_ratio는 약한 차순위가 floor만 겨우 넘어 끼는
        over-add를 막는다(결정적 — 동점 사전순)."""
        above = [(nt, sc) for nt, sc in scores.items() if sc >= self._threshold]
        if not above:
            return ()
        cutoff = max(sc for _, sc in above) * self._top_ratio
        kept = [(nt, sc) for nt, sc in above if sc >= cutoff]
        kept.sort(key=lambda x: (-x[1], x[0]))
        return tuple(nt for nt, _ in kept)
