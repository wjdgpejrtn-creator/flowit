"""IntentAnalyzerService.analyze — 편집 잠금(상태 인지 draft↔refine) (#369).

확인 대기 draft가 있는 세션은 **편집 모드**다(조장 지시 2026-06-10). draft/refine/미분류
발화는 전부 기존 draft 수정(refine)으로 **결정적 확정** — 새 워크플로우 생성을 잠근다.
정규식만 쓰던 구조가 수정 발화("...로 바꿔줘")를 새 생성으로 오분류해 4노드 워크플로우가
2노드로 재생성되던 회귀를, 상태(`has_pending_draft`) 기반 결정적 잠금으로 해소한다.
LLM 분류는 제거(작은 모델 오분류 차단 + 핫패스 지연 0).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from common_schemas.enums import IntentType

from ai_agent.domain.ports.llm_port import LLMPort
from ai_agent.domain.services.intent_analyzer_service import IntentAnalyzerService


def _msgs(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


def _service() -> tuple[IntentAnalyzerService, AsyncMock]:
    llm = AsyncMock(spec=LLMPort)
    return IntentAnalyzerService(llm), llm


# ── 무상태·명시적 의도: 정규식 확정, LLM 미호출 (draft 유무 무관) ────────────────
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
    # 명시적 의도는 draft 대기 중이어도 편집 잠금 전에 단락된다(실행/취소/인사 등은 편집 아님).
    svc, llm = _service()
    result = await svc.analyze(_msgs(text), context={"has_pending_draft": True})
    assert result is not None and result.intent == expected
    llm.generate_structured.assert_not_awaited()


# ── 편집 잠금: draft 존재 시 모든 구성 발화 → REFINE (결정적, LLM 0) ──────────────
@pytest.mark.parametrize(
    "text",
    [
        "슬랙 채널을 #general로 해줘",          # 편집동사 없는 자연스러운 수정
        "url을 naver.com으로 바꿔줘",             # 명시적 수정
        "이거 slack 말고 gmail로 보내는 걸로 수정해줘",  # 실제 #369 발화
        "매주 월요일 9시에 시트 읽어서 슬랙으로 보내줘",  # draft처럼 보여도 잠금 → refine
        "A노드 url naver.com",                    # 정규식 미분류여도 draft 존재 시 refine
    ],
)
@pytest.mark.asyncio
async def test_pending_draft_locks_all_construction_to_refine(text):
    svc, llm = _service()
    result = await svc.analyze(_msgs(text), context={"has_pending_draft": True})
    assert result is not None and result.intent == IntentType.REFINE
    assert result.confidence == 1.0
    llm.generate_structured.assert_not_awaited()  # 결정적 — 분류 LLM 호출 없음


# ── draft 없음: refine 불가 → 새 생성(draft)으로 교정, LLM 미호출 ─────────────────
@pytest.mark.asyncio
async def test_same_utterance_without_pending_draft_classifies_draft_no_llm():
    svc, llm = _service()
    result = await svc.analyze(_msgs("슬랙 채널을 #general로 해줘"), context={"has_pending_draft": False})
    assert result.intent == IntentType.DRAFT
    llm.generate_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_refine_verb_without_pending_draft_corrected_to_draft():
    # 불변식: refine은 draft가 있어야 성립. draft 없는데 "바꿔줘"면 새 생성으로 교정.
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
    result = await svc.analyze(_msgs("A노드 url naver.com"), context={})  # 키워드 무매칭, 상태 무
    assert result is None
    llm.generate_structured.assert_not_awaited()
