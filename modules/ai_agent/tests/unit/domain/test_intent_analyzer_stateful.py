"""IntentAnalyzerService.analyze — 상태 인지 draft↔refine 분류 (#369).

draft/refine는 발화 표면만으론 못 가르는 상태 의존 의도다. 같은 "채널 #general로 해줘"가
세션에 확인 대기 draft가 있으면 refine, 없으면 draft. 정규식만 쓰던 구조가 수정 발화를
새 생성(draft)으로 오분류하던 버그를, 상태(`has_pending_draft`)를 Gemma에 주입해 해소한다.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from common_schemas.enums import IntentType

from ai_agent.domain.ports.llm_port import LLMPort
from ai_agent.domain.services.intent_analyzer_service import (
    IntentAnalyzerService,
    _IntentLLMResponse,
)


def _msgs(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


def _service(llm_intent: str | None = None, raises: bool = False) -> tuple[IntentAnalyzerService, AsyncMock]:
    llm = AsyncMock(spec=LLMPort)
    if raises:
        llm.generate_structured = AsyncMock(side_effect=RuntimeError("LLM down"))
    elif llm_intent is not None:
        llm.generate_structured = AsyncMock(
            return_value=_IntentLLMResponse(intent=llm_intent, confidence=0.9)
        )
    return IntentAnalyzerService(llm), llm


# ── 무상태·명시적 의도: 정규식 확정, LLM 미호출 ────────────────────────────────
@pytest.mark.parametrize(
    "text,expected",
    [
        ("취소", IntentType.CONTROL),
        ("실행해줘", IntentType.WORKFLOW_EXECUTE),
        ("안녕", IntentType.CHITCHAT),
        ("이대로 진행", IntentType.PROPOSE),
        ("스킬 만들어줘", IntentType.BUILD_SKILL),
    ],
)
@pytest.mark.asyncio
async def test_stateless_intents_use_regex_without_llm(text, expected):
    svc, llm = _service()
    result = await svc.analyze(_msgs(text), context={"has_pending_draft": True})
    assert result is not None and result.intent == expected
    llm.generate_structured.assert_not_awaited()  # 상태 무관 → LLM 불필요


# ── 핵심 버그: 편집동사 없는 수정 발화 ────────────────────────────────────────
@pytest.mark.asyncio
async def test_ambiguous_edit_with_pending_draft_classifies_refine():
    # "채널 #general로 해줘" → 정규식이라면 '해줘'에 걸려 draft. 상태 주입 + Gemma로 refine.
    svc, llm = _service(llm_intent="refine")
    result = await svc.analyze(_msgs("슬랙 채널을 #general로 해줘"), context={"has_pending_draft": True})
    assert result.intent == IntentType.REFINE
    llm.generate_structured.assert_awaited_once()


@pytest.mark.asyncio
async def test_same_utterance_without_pending_draft_classifies_draft_no_llm():
    # draft 없음 → refine 불가 → create 핫패스에 Gemma 호출 없이 정규식 draft로 확정.
    svc, llm = _service()
    result = await svc.analyze(_msgs("슬랙 채널을 #general로 해줘"), context={"has_pending_draft": False})
    assert result.intent == IntentType.DRAFT
    llm.generate_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_refine_verb_without_pending_draft_corrected_to_draft():
    # 불변식: refine은 draft가 있어야 성립. draft 없는데 "바꿔줘"면 새 생성으로 교정, LLM 불필요.
    svc, llm = _service()
    result = await svc.analyze(_msgs("url을 naver.com으로 바꿔줘"), context={"has_pending_draft": False})
    assert result.intent == IntentType.DRAFT
    llm.generate_structured.assert_not_awaited()


# ── 무상태 호출부(supervisor): context에 키 없음 → 정규식, LLM 미호출 ──────────
@pytest.mark.asyncio
async def test_no_state_context_falls_back_to_regex_no_llm():
    svc, llm = _service()
    result = await svc.analyze(_msgs("슬랙 채널을 #general로 해줘"), context={})
    assert result.intent == IntentType.DRAFT  # 정규식 '해줘' → draft (supervisor 라우팅엔 충분)
    llm.generate_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_unclassified_without_context_returns_none():
    svc, llm = _service()
    result = await svc.analyze(_msgs("A노드 url naver.com"), context={})  # 키워드 무매칭
    assert result is None
    llm.generate_structured.assert_not_awaited()


# ── LLM 실패/미상값 → 상태 기반 안전 폴백 ─────────────────────────────────────
@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_refine_when_draft_pending():
    svc, _ = _service(raises=True)
    result = await svc.analyze(_msgs("이 부분 손봐줘"), context={"has_pending_draft": True})
    assert result.intent == IntentType.REFINE  # draft 대기 중이면 수정으로 안전 폴백
    assert result.confidence <= 0.5


@pytest.mark.asyncio
async def test_llm_garbage_intent_coerced_to_safe_default():
    svc, _ = _service(llm_intent="нонсенс")  # IntentType로 변환 불가
    result = await svc.analyze(_msgs("바꿀 게 있어"), context={"has_pending_draft": True})
    assert result.intent == IntentType.REFINE
