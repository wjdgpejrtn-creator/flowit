"""IntentAnalyzerService.analyze — Gemma 4 1차 분류 + 편집 잠금(상태 의존) + 정규식 fallback.

1차 의도 분류는 Gemma 4(LLM)가 한다 — 자연어는 규칙 몇 개로 못 가른다("스킬 만들고 싶어"
같은 표현 변주). 정규식은 llm-base 다운 시 비상 fallback 전용.

draft↔refine은 텍스트로 못 푸는 **세션 상태 의존** 축이라 Gemma가 아니라 편집 잠금
(`has_pending_draft`)으로 결정적으로 푼다(#369 회귀 방지) — Gemma 분류의 보완재.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from common_schemas.enums import IntentType

from ai_agent.domain.ports.llm_port import LLMPort
from ai_agent.domain.services.intent_analyzer_service import (
    IntentAnalyzerService,
    _IntentClassification,
)


def _msgs(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


def _service() -> tuple[IntentAnalyzerService, AsyncMock]:
    llm = AsyncMock(spec=LLMPort)
    return IntentAnalyzerService(llm), llm


def _llm_returns(llm: AsyncMock, intent: str) -> None:
    llm.generate_structured.return_value = _IntentClassification(intent=intent)


# ── Gemma가 1차 분류기: 분류 결과를 그대로 사용 ────────────────────────────────
@pytest.mark.parametrize(
    "intent",
    ["build_skill", "chitchat", "control", "workflow_execute", "info_question", "propose"],
)
@pytest.mark.asyncio
async def test_llm_classifies_base_intent(intent: str):
    svc, llm = _service()
    _llm_returns(llm, intent)
    result = await svc.analyze(_msgs("아무 발화든"), context={})
    assert result is not None and result.intent.value == intent
    llm.generate_structured.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_skill_varied_phrasing_via_llm():
    # 핵심 회귀(#496): "나 스킬 만들고 싶어"를 Gemma가 build_skill로 분류 → 위저드 발동.
    # (정규식 단독 시절엔 '만들고'를 못 잡아 general_chat으로 샜다.)
    svc, llm = _service()
    _llm_returns(llm, "build_skill")
    result = await svc.analyze(_msgs("나 스킬 만들고 싶어"), context={"has_pending_draft": False})
    assert result.intent == IntentType.BUILD_SKILL


# ── 편집 잠금: 확인 대기 draft 있으면 구성 발화 → REFINE (상태 기반, Gemma 무관) ──
@pytest.mark.asyncio
async def test_pending_draft_locks_construction_to_refine():
    # Gemma가 draft로 분류해도, 확인 대기 draft가 있으면 편집 잠금 → REFINE.
    svc, llm = _service()
    _llm_returns(llm, "draft")
    result = await svc.analyze(
        _msgs("슬랙 채널을 #general로 해줘"), context={"has_pending_draft": True}
    )
    assert result.intent == IntentType.REFINE
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_stateless_intent_bypasses_edit_lock_even_with_pending_draft():
    # 무상태 의도(취소/실행/스킬빌드 등)는 draft 대기 중이어도 잠금 단락 — 편집이 아니다.
    svc, llm = _service()
    _llm_returns(llm, "control")
    result = await svc.analyze(_msgs("취소"), context={"has_pending_draft": True})
    assert result.intent == IntentType.CONTROL


# ── draft 없음: refine 불가 → 새 생성(draft)으로 교정 ──────────────────────────
@pytest.mark.asyncio
async def test_refine_without_pending_draft_corrected_to_draft():
    svc, llm = _service()
    _llm_returns(llm, "refine")
    result = await svc.analyze(
        _msgs("url을 naver.com으로 바꿔줘"), context={"has_pending_draft": False}
    )
    assert result.intent == IntentType.DRAFT


@pytest.mark.asyncio
async def test_no_state_context_uses_llm_result():
    # 무상태 호출부(supervisor): context에 키 없음 → Gemma 분류 그대로(draft/refine 동일 레시피).
    svc, llm = _service()
    _llm_returns(llm, "draft")
    result = await svc.analyze(_msgs("슬랙 알림 자동화 만들어줘"), context={})
    assert result.intent == IntentType.DRAFT


# ── llm-base 다운/타임아웃 → 정규식 fallback (회복력) ──────────────────────────
@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_regex():
    svc, llm = _service()
    llm.generate_structured.side_effect = RuntimeError("llm-base down")
    result = await svc.analyze(_msgs("스킬 만들어줘"), context={})
    assert result is not None and result.intent == IntentType.BUILD_SKILL  # 정규식 fallback이 잡음


@pytest.mark.asyncio
async def test_llm_failure_unclassifiable_returns_none():
    svc, llm = _service()
    llm.generate_structured.side_effect = RuntimeError("down")
    result = await svc.analyze(_msgs("xkcd qwerty"), context={})
    assert result is None


@pytest.mark.asyncio
async def test_llm_failure_pending_draft_still_locks_to_refine():
    # llm-base 다운이어도 편집 잠금은 상태 기반이라 그대로 동작(REFINE).
    svc, llm = _service()
    llm.generate_structured.side_effect = RuntimeError("down")
    result = await svc.analyze(
        _msgs("A노드 url naver.com"), context={"has_pending_draft": True}
    )
    assert result.intent == IntentType.REFINE
