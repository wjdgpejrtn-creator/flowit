"""앙상블 슬롯 채움 단위테스트 (ADR-0026 §6.6 Phase 2 — 노드 선택 의미화).

순수 voter(lexical/semantic/ontology) + 결합/임계/기권 + LLM 지연 escalation(mock)을
결정적으로 검증한다. LLM·Neo4j 실인프라 불요 — 신호는 VoteContext에 데이터로 주입.
"""
from __future__ import annotations

import pytest

from ai_agent.domain.services.skeleton_entity_extractor import SkeletonEntityExtractor
from ai_agent.domain.services.skeleton_library import ROLE_CANDIDATE_POOLS
from ai_agent.domain.services.slot_ensemble import EnsembleSlotResolver
from ai_agent.domain.services.slot_voters import (
    LexicalVoter,
    OntologyVoter,
    SemanticVoter,
    VoteContext,
)
from ai_agent.domain.value_objects.skeleton import SlotRole

_SOURCE_POOL = ROLE_CANDIDATE_POOLS[SlotRole.SOURCE]
_SINK_POOL = ROLE_CANDIDATE_POOLS[SlotRole.SINK]
_EX = SkeletonEntityExtractor()


def _ctx(utterance: str, ranked: list[str] | None = None, allowed: set[str] | None = None) -> VoteContext:
    return VoteContext(
        utterance=utterance,
        entities=_EX.extract(utterance.lower()),
        ranked_candidates=tuple(ranked or ()),
        ontology_allowed=frozenset(allowed or set()),
    )


# ── voter 단위 ──────────────────────────────────────────────────────────────
def test_lexical_voter_scores_matched_node_in_pool() -> None:
    ctx = _ctx("매주 광고 시트 읽어서 슬랙으로")
    v = LexicalVoter()
    assert v.vote(ctx, SlotRole.SOURCE, _SOURCE_POOL) == {"google_sheets_read": 1.0}
    assert v.vote(ctx, SlotRole.SINK, _SINK_POOL) == {"slack_post_message": 1.0}


def test_semantic_voter_reciprocal_rank_within_role_pool() -> None:
    # 역할 풀로 필터 후 그 안 순위로 1/(1+idx). pool 밖(anthropic_chat)은 무시.
    ctx = _ctx("x", ranked=["gmail_read", "anthropic_chat", "google_sheets_read"])
    scores = SemanticVoter().vote(ctx, SlotRole.SOURCE, _SOURCE_POOL)
    assert scores["gmail_read"] == 1.0
    assert scores["google_sheets_read"] == 0.5  # source 중 2번째
    assert "anthropic_chat" not in scores


def test_ontology_voter_degrades_to_noop_without_subgraph() -> None:
    ctx = _ctx("x", ranked=["gmail_read"])
    assert OntologyVoter().vote(ctx, SlotRole.SOURCE, _SOURCE_POOL) == {}


def test_ontology_voter_scores_subgraph_members() -> None:
    ctx = _ctx("x", allowed={"gmail_read", "anthropic_chat"})
    scores = OntologyVoter().vote(ctx, SlotRole.SOURCE, _SOURCE_POOL)
    assert scores == {"gmail_read": 1.0}  # pool ∩ allowed만


# ── 앙상블 결합/기권 ─────────────────────────────────────────────────────────
async def _resolve(resolver, utterance, ranked=None, allowed=None):
    return await resolver.resolve(
        utterance, tuple(ranked or ()), frozenset(allowed or set())
    )


@pytest.mark.asyncio
async def test_ensemble_resolves_gmail_read_from_semantic_when_lexical_silent() -> None:
    # 이슈 직격: "gmail에서 …" source 렉시컬 미인식 → 의미검색 1등(gmail_read)이 슬롯을 차지.
    # google_sheets_read는 하위 랭킹이라 임계 미달 → 배제(오선택 차단).
    resolver = EnsembleSlotResolver([LexicalVoter(), SemanticVoter(), OntologyVoter()])
    resolved = await _resolve(
        resolver,
        "내 gmail에서 결제 내역 모아서 보고서 작성해서 pdf로 gmail로 보내줘",
        ranked=["gmail_read", "manual_trigger", "google_sheets_read", "pdf_generate", "gmail_send"],
    )
    assert resolved.for_role(SlotRole.SOURCE) == ("gmail_read",)
    assert "google_sheets_read" not in resolved.for_role(SlotRole.SOURCE)
    # sink는 렉시컬(gmail_send·pdf_generate)이 잡아 둘 다 채워진다.
    assert set(resolved.for_role(SlotRole.SINK)) == {"gmail_send", "pdf_generate"}


@pytest.mark.asyncio
async def test_lexical_hit_always_survives_threshold() -> None:
    # 렉시컬 적중(weight 1.0)은 의미신호가 0이어도 임계(0.5) 통과 — 정밀 보존.
    resolved = await _resolve(
        EnsembleSlotResolver([LexicalVoter(), SemanticVoter()]), "매주 광고 시트 읽어서 슬랙으로"
    )
    assert resolved.for_role(SlotRole.SOURCE) == ("google_sheets_read",)
    assert resolved.for_role(SlotRole.SINK) == ("slack_post_message",)


@pytest.mark.asyncio
async def test_weak_signal_alone_abstains() -> None:
    # 온톨로지 멤버십(0.25)만으로는 임계 미달 → 기권(빈 픽). 약신호 단독 바인딩 방지.
    resolved = await _resolve(
        EnsembleSlotResolver([LexicalVoter(), SemanticVoter(), OntologyVoter()]),
        "아무 발화", allowed={"google_sheets_read"},
    )
    assert not resolved.has_pick(SlotRole.SOURCE)


@pytest.mark.asyncio
async def test_trace_records_contributors_and_escalation() -> None:
    # trace sink — lexical 무음 + semantic이 캐리한 source 결정의 귀속/마진 기록.
    from ai_agent.domain.services.slot_ensemble import SlotDecision
    trace: list[SlotDecision] = []
    resolver = EnsembleSlotResolver([LexicalVoter(), SemanticVoter(), OntologyVoter()])
    # "우편함"은 렉시컬 미등록 → semantic(gmail_read 1등)이 캐리.
    await resolver.resolve(
        "내 우편함 싹 뒤져서 슬랙으로",
        tuple(["gmail_read", "google_sheets_read", "slack_post_message"]),
        frozenset(),
        trace=trace,
    )
    src = next(d for d in trace if d.role == SlotRole.SOURCE)
    assert src.picks == ("gmail_read",)
    assert "semantic" in src.contributors and "lexical" not in src.contributors  # 의미가 캐리
    assert src.escalated is False  # 싼 voter로 해소 → LLM 미개입
    assert src.margin > 0


@pytest.mark.asyncio
async def test_trace_marks_llm_escalation() -> None:
    from ai_agent.domain.services.slot_ensemble import SlotDecision
    trace: list[SlotDecision] = []
    mapper = _StubMapper({SlotRole.SOURCE: (("gmail_read", 1.0),)})
    resolver = EnsembleSlotResolver([LexicalVoter(), SemanticVoter()], llm_mapper=mapper)
    await resolver.resolve("그것들 다 모아서 슬랙으로 정리해줘", (), frozenset(), trace=trace)
    src = next(d for d in trace if d.role == SlotRole.SOURCE)
    assert src.escalated is True and "llm" in src.contributors and src.picks == ("gmail_read",)


@pytest.mark.asyncio
async def test_top_ratio_suppresses_weak_secondary_source() -> None:
    # 온톨로지 멤버십(0.25)에 업힌 차순위 source(google_sheets_read=0.55)가 floor(0.5)는 넘어도
    # 최고점(gmail_read=0.85)의 70%(=0.595) 미만이라 탈락 — over-add(잉여 노드) 방지.
    resolved = await _resolve(
        EnsembleSlotResolver([LexicalVoter(), SemanticVoter(), OntologyVoter()]),
        "내 gmail에서 결제 내역 모아서 슬랙으로",
        ranked=["gmail_read", "google_sheets_read"],
        allowed={"gmail_read", "google_sheets_read"},
    )
    assert resolved.for_role(SlotRole.SOURCE) == ("gmail_read",)


@pytest.mark.asyncio
async def test_resolver_excludes_semantic_bled_sink_variant() -> None:
    # slack_read가 source(읽기)인데 슬랙 send-cue 없음 → SemanticVoter가 slack_post_message를
    # sink 상위로 올리고 ontology에 있어도 resolver가 풀에서 제외(렉시컬뿐 아니라 semantic 표까지
    # 차단). 진짜 sink(email)만 남는다 — sink over-match(소스-블리드) 완전 차단.
    resolver = EnsembleSlotResolver([LexicalVoter(), SemanticVoter(), OntologyVoter()])
    resolved = await _resolve(
        resolver,
        "슬랙 공지 채널 글들 읽어서 요약해서 이메일로 보내줘",
        ranked=["slack_read", "slack_post_message", "slack_notify", "email_send"],
        allowed={"slack_post_message", "email_send"},
    )
    assert resolved.for_role(SlotRole.SOURCE) == ("slack_read",)
    snk = resolved.for_role(SlotRole.SINK)
    assert "slack_post_message" not in snk and "slack_notify" not in snk
    assert "email_send" in snk


@pytest.mark.asyncio
async def test_resolver_skips_transform_and_trigger() -> None:
    # SOURCE/SINK만 앙상블 — transform(_AI 항상 후보라 비변별)·trigger는 조립기 기존 경로.
    resolved = await _resolve(
        EnsembleSlotResolver([LexicalVoter(), SemanticVoter()]),
        "요약해줘", ranked=["anthropic_chat", "schedule_trigger"],
    )
    assert not resolved.has_pick(SlotRole.TRANSFORM)
    assert not resolved.has_pick(SlotRole.TRIGGER)


@pytest.mark.asyncio
async def test_select_is_deterministic_on_ties() -> None:
    # 동점은 node_type 사전순 — 같은 입력 같은 출력.
    resolver = EnsembleSlotResolver([OntologyVoter(weight=1.0)])  # weight↑로 임계 통과
    r1 = await _resolve(resolver, "x", allowed=set(_SOURCE_POOL))
    r2 = await _resolve(resolver, "x", allowed=set(_SOURCE_POOL))
    assert r1.for_role(SlotRole.SOURCE) == r2.for_role(SlotRole.SOURCE)
    assert list(r1.for_role(SlotRole.SOURCE)) == sorted(r1.for_role(SlotRole.SOURCE))


# ── LLM 지연 escalation (mock) ────────────────────────────────────────────────
class _StubMapper:
    """싼 voter가 기권한 역할만 호출되는지 + 픽을 폴딩하는지 검증용."""

    def __init__(self, ret: dict[SlotRole, tuple[tuple[str, float], ...]]) -> None:
        self._ret = ret
        self.called_with: dict[SlotRole, tuple[str, ...]] | None = None

    async def map_slots(self, utterance, roles_and_pools):
        self.called_with = roles_and_pools
        return self._ret


@pytest.mark.asyncio
async def test_llm_escalates_only_uncertain_roles_and_folds_pick() -> None:
    # 싼 voter는 source 기권(렉시컬·랭킹 무신호), sink는 렉시컬로 확정. LLM은 source만 받아
    # gmail_read를 confidence 1.0으로 매핑 → 폴딩 후 source 바인딩. sink는 LLM 미escalate.
    mapper = _StubMapper({SlotRole.SOURCE: (("gmail_read", 1.0),)})
    resolver = EnsembleSlotResolver([LexicalVoter(), SemanticVoter()], llm_mapper=mapper)
    resolved = await _resolve(resolver, "그것들 다 모아서 슬랙으로 정리해줘")
    assert mapper.called_with is not None
    assert SlotRole.SOURCE in mapper.called_with and SlotRole.SINK not in mapper.called_with
    assert resolved.for_role(SlotRole.SOURCE) == ("gmail_read",)
    assert resolved.for_role(SlotRole.SINK) == ("slack_post_message",)


@pytest.mark.asyncio
async def test_llm_pick_outside_pool_discarded() -> None:
    # LLM이 풀 밖 node_type을 주면 폐기(환각 가드).
    mapper = _StubMapper({SlotRole.SOURCE: (("not_a_real_node", 1.0),)})
    resolved = await _resolve(
        EnsembleSlotResolver([LexicalVoter()], llm_mapper=mapper), "뭔가 가져와서 어딘가로"
    )
    assert not resolved.has_pick(SlotRole.SOURCE)


@pytest.mark.asyncio
async def test_no_llm_mapper_degrades_to_cheap_voters() -> None:
    # llm_mapper 미주입 → 싼 voter만으로 동작(graceful degrade), 에러 없음.
    resolved = await _resolve(
        EnsembleSlotResolver([LexicalVoter(), SemanticVoter()]),
        "매주 시트 읽어서 슬랙으로", ranked=["google_sheets_read", "slack_post_message"],
    )
    assert resolved.for_role(SlotRole.SOURCE) == ("google_sheets_read",)
