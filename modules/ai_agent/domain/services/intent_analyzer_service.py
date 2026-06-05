from __future__ import annotations

import json
import re
from typing import Any

from common_schemas import IntentResult
from common_schemas.enums import IntentType
from common_schemas.exceptions import ExecutionError

from ..ports.llm_port import LLMPort
from ..value_objects.route_plan import RECIPE_SKILL_THEN_COMPOSE

# ── 키워드 기반 fast classifier ──────────────────────────────────────────────
# 정규식 매칭 ~90% → LLM fallback ~10%

_CONTROL_RE = re.compile(
    r"(취소|초기화|리셋|reset|중단|멈춰|stop|처음부터|다시\s*시작)", re.IGNORECASE
)
_EXECUTE_RE = re.compile(
    r"(실행\s*(해줘|해|시작|go|run)|run\s*it|바로\s*실행|지금\s*실행)", re.IGNORECASE
)
_CHITCHAT_RE = re.compile(
    r"^(안녕|hi|hello|ㅎㅇ|반가|수고|고마워|감사|잘\s*했|굿|좋아요?|ㄱㅅ|ㄱㅊ|ㅂㅂ|bye|잘\s*있어)[!~ㅋㅎ.]*$",
    re.IGNORECASE,
)
_INFO_RE = re.compile(
    r"(이게\s*뭐야?|어떻게\s*(돼?|작동|사용)|설명\s*(해줘?|해주세요?)|무슨\s*기능|뭘\s*할\s*수\s*있|어떤\s*워크플로우|목록|리스트|보여줘)",
    re.IGNORECASE,
)
_PROPOSE_RE = re.compile(
    r"(이대로|그대로\s*(해줘?|진행)|승인|approve)",
    re.IGNORECASE,
)
_REFINE_RE = re.compile(
    r"(수정|바꿔|변경|고쳐|다시\s*만들어|추가\s*(해줘?|해)|빼|제거|삭제|대신|아니라|말고)",
    re.IGNORECASE,
)
_BUILD_SKILL_RE = re.compile(
    r"(스킬|skill)\s*(만들어|빌드|build|등록|추가)",
    re.IGNORECASE,
)
_DRAFT_RE = re.compile(
    r"(만들어|생성|워크플로우|자동화|자동\s*으로|매주|매일|스케줄|알림|보내줘|보내|알려줘|처리해줘?|해줘)",
    re.IGNORECASE,
)


# ── 복합 의도(레시피) 분류 ───────────────────────────────────────────────────
# 한 발화에 스킬 생성 + 그 스킬로 워크플로우 작성이 모두 담긴 경우 → skill_then_compose.
# 보수적: 세 신호(스킬 빌드 / compose 대상 / 순차 연결어)가 모두 있어야 복합으로 본다.
# 애매하면 단일 의도로 폴백 (오탐 시 사용자 흐름이 더 어색해지므로).
_SKILL_SIGNAL_RE = re.compile(r"(스킬|skill)\s*(을|를)?\s*(만들|만든|빌드|build|등록|생성)", re.IGNORECASE)
_COMPOSE_SIGNAL_RE = re.compile(r"(워크플로우|workflow|자동화|automation|플로우)", re.IGNORECASE)
_CHAIN_CONNECTIVE_RE = re.compile(
    r"(만들어서|만들고|만든\s*뒤|만든\s*다음|등록하고|등록해서|해서|그걸로|그\s*스킬로|이용해서?|사용해서?|로\s*만들|연결)",
    re.IGNORECASE,
)


def _is_skill_then_compose(message: str) -> bool:
    """스킬 빌드 → 워크플로우 작성 복합 발화 여부 (세 신호 동시 충족)."""
    return bool(
        _SKILL_SIGNAL_RE.search(message)
        and _COMPOSE_SIGNAL_RE.search(message)
        and _CHAIN_CONNECTIVE_RE.search(message)
    )


def classify_recipe(message: str, intent: IntentType | None) -> str | None:
    """라우팅 레시피 키 산출 (순수 함수, LLM 무관).

    단일 의도는 ``intent.value``를 그대로 키로 쓰고, 화이트리스트 복합 발화만
    별도 키를 반환한다. 미분류(intent None & 복합 아님)는 None → general_chat.

    supervisor 루프가 이 키로 ``make_plan``을 호출한다. 단일 의도는 1-스텝
    레시피라 승격 전 1-홉 동작과 동일하다 (회귀 안전).
    """
    if _is_skill_then_compose(message):
        return RECIPE_SKILL_THEN_COMPOSE
    if intent is None:
        return None
    return intent.value


def _fast_classify(message: str) -> IntentType | None:
    """키워드/정규식으로 즉시 분류. 확신 없으면 None 반환 → LLM fallback."""
    msg = message.strip()

    if _CONTROL_RE.search(msg):
        return IntentType.CONTROL
    if _EXECUTE_RE.search(msg):
        return IntentType.WORKFLOW_EXECUTE
    if _CHITCHAT_RE.match(msg):
        return IntentType.CHITCHAT
    if _PROPOSE_RE.search(msg) and len(msg) <= 30:
        return IntentType.PROPOSE
    if _INFO_RE.search(msg):
        return IntentType.INFO_QUESTION
    if _BUILD_SKILL_RE.search(msg):
        return IntentType.BUILD_SKILL
    if _REFINE_RE.search(msg):
        return IntentType.REFINE
    if _DRAFT_RE.search(msg) and len(msg) >= 10:
        return IntentType.DRAFT
    return None


# ── LLM fallback prompt ───────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an intent classifier for a workflow automation assistant.
Classify the user's latest message into one of these intents:
- chitchat: greeting, thanks, casual conversation ("안녕", "고마워")
- control: cancel, reset, stop ("취소", "초기화", "중단")
- workflow_execute: user wants to run/execute the current workflow ("실행해줘")
- info_question: asking about features or existing workflows ("이게 뭐야", "어떻게 써")
- draft: user wants a NEW workflow created
- refine: user wants to MODIFY an existing workflow draft
- clarify: input is ambiguous, needs more information
- propose: user accepts/approves the current proposal
- build_skill: user wants to build a reusable skill

When intent is "build_skill", include source_type in analyzed_entities:
- "industry_default": user mentions an industry → include "industry_code"
- "functional_domain": user mentions a department → include "domain_code"
- "sop": user provides a SOP document text

Return JSON only, no explanation:
{"intent": "<intent>", "confidence": <0.0-1.0>, "analyzed_entities": {}}
"""


class IntentAnalyzerService:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def analyze(self, messages: list[dict[str, Any]], context: dict[str, Any]) -> IntentResult | None:
        user_message = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_message = m.get("content", "")
                break

        # fast-path: 키워드 분류 (LLM 0 call)
        fast_intent = _fast_classify(user_message)
        if fast_intent is not None:
            return IntentResult(
                intent=fast_intent,
                confidence=0.95,
                analyzed_entities={},
            )

        # 미분류 → None 반환 (supervisor가 general_chat으로 처리)
        # LLM 분류 호출 제거 — 분류 실패 시 응답 생성 LLM으로 흡수
        return None
