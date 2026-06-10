from __future__ import annotations

from collections import defaultdict

from ..ports.slot_mapper_port import SlotMapperPort
from ..value_objects.skeleton import ResolvedSlots, SlotRole
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

# 앙상블이 의미신호로 채우는 역할 — 나머지(transform/trigger/control)는 조립기 기존 경로.
_RESOLVE_ROLES: tuple[SlotRole, ...] = (SlotRole.SOURCE, SlotRole.SINK)

# 후보가 슬롯에 바인딩되는 가중합 절대 하한. semantic 1등 단독(weight 0.6)은 넘고,
# ontology 멤버십 단독(weight 0.25)은 못 넘게 — 약신호 단독 바인딩 방지. 골든셋 튜닝 대상.
_BIND_THRESHOLD = 0.5
# LLM voter(escalation) 가중치 — 강신호.
_LLM_WEIGHT = 1.0


class EnsembleSlotResolver:
    """싼 voter 가중투표 + (필요 시) LLM escalation으로 역할별 노드를 확정한다."""

    def __init__(
        self,
        voters: list[SlotVoter],
        llm_mapper: SlotMapperPort | None = None,
        *,
        resolve_roles: tuple[SlotRole, ...] = _RESOLVE_ROLES,
        bind_threshold: float = _BIND_THRESHOLD,
        llm_weight: float = _LLM_WEIGHT,
    ) -> None:
        self._voters = voters
        self._llm_mapper = llm_mapper
        self._roles = resolve_roles
        self._threshold = bind_threshold
        self._llm_weight = llm_weight

    async def resolve(self, ctx: VoteContext) -> ResolvedSlots:
        """역할별 앙상블 픽을 계산. 싼 voter로 먼저 풀고, 기권한 역할만 LLM으로 escalate."""
        by_role: dict[SlotRole, tuple[str, ...]] = {}
        uncertain: dict[SlotRole, tuple[str, ...]] = {}

        for role in self._roles:
            pool = ROLE_CANDIDATE_POOLS.get(role, ())
            if not pool:
                continue
            picks = self._select(self._combine(ctx, role, pool))
            if picks:
                by_role[role] = picks
            else:
                uncertain[role] = pool

        # 지연 escalation — 싼 voter가 확신 못 한 역할만 LLM 1콜로 재시도.
        if uncertain and self._llm_mapper is not None:
            llm = await self._llm_mapper.map_slots(ctx.utterance, uncertain)
            for role, pool in uncertain.items():
                extra = {nt: conf for nt, conf in llm.get(role, ()) if nt in set(pool)}
                picks = self._select(self._combine(ctx, role, pool, extra=extra))
                if picks:
                    by_role[role] = picks

        return ResolvedSlots(by_role=by_role)

    def _combine(
        self,
        ctx: VoteContext,
        role: SlotRole,
        pool: tuple[str, ...],
        extra: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """voter별 점수를 가중합. ``extra``(LLM confidence)는 llm_weight로 가산."""
        scores: dict[str, float] = defaultdict(float)
        for voter in self._voters:
            for nt, s in voter.vote(ctx, role, pool).items():
                scores[nt] += voter.weight * s
        if extra:
            for nt, conf in extra.items():
                scores[nt] += self._llm_weight * conf
        return scores

    def _select(self, scores: dict[str, float]) -> tuple[str, ...]:
        """임계 이상 후보를 점수 내림차순(동점은 node_type 사전순 — 결정적)으로 반환."""
        above = [(nt, sc) for nt, sc in scores.items() if sc >= self._threshold]
        above.sort(key=lambda x: (-x[1], x[0]))
        return tuple(nt for nt, _ in above)
