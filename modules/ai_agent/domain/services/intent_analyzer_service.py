from __future__ import annotations

import re
from typing import Any

from common_schemas import IntentResult
from common_schemas.enums import IntentType
from pydantic import BaseModel, Field

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


class _IntentLLMResponse(BaseModel):
    """Gemma 분류 출력 (generate_structured 스키마)."""

    intent: str
    confidence: float = 0.8
    analyzed_entities: dict[str, Any] = Field(default_factory=dict)


# draft/refine는 **상태 의존** 의도 — 같은 발화도 세션에 확인 대기 draft가 있는지에 따라
# 정답이 갈린다("채널 #general로 해줘" = draft無→새 생성 / draft有→수정). 정규식만으론
# 절대 못 가르므로(#369) 이 둘로 분류되거나 미분류면 상태를 주입해 Gemma로 정밀 재분류한다.
_STATEFUL_INTENTS = frozenset({IntentType.DRAFT, IntentType.REFINE})


def _coerce_intent(value: str) -> IntentType | None:
    """LLM이 돌려준 문자열을 IntentType으로. 미상값은 None."""
    try:
        return IntentType(value.strip().lower())
    except (ValueError, AttributeError):
        return None


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

        # 무상태·명시적 의도(제어/실행/인사/승인/안내/스킬빌드)는 정규식으로 확정한다 —
        # 발화 표면만으로 정답이 정해지므로 LLM이 불필요하다.
        if fast_intent is not None and fast_intent not in _STATEFUL_INTENTS:
            return IntentResult(intent=fast_intent, confidence=0.95, analyzed_entities={})

        # 여기 도달 = draft/refine/미분류 = '워크플로우 구성' 의도(상태 의존).
        has_draft = context.get("has_pending_draft")
        if has_draft is not None:
            # 핵심 불변식: refine은 확인 대기 draft가 있어야만 성립한다.
            if has_draft:
                # draft 존재 → draft↔refine이 진짜 모호 → Gemma 상태 인지 분류(#369).
                return await self._llm_classify(user_message, True, fallback=fast_intent)
            # draft 없음 → refine 불가능 → refine 오탐은 새 생성(draft)으로 교정한다.
            # create 핫패스엔 Gemma 호출을 더하지 않는다(불필요한 지연 방지).
            if fast_intent is IntentType.REFINE:
                fast_intent = IntentType.DRAFT

        # 무상태 호출부(supervisor)이거나 draft 없는 경우 — 정규식 결과 그대로.
        # supervisor는 draft/refine이 동일 레시피(→COMPOSER)라 정규식으로 충분하다.
        if fast_intent is not None:
            return IntentResult(intent=fast_intent, confidence=0.95, analyzed_entities={})
        return None

    async def _llm_classify(
        self, user_message: str, has_pending_draft: bool, fallback: IntentType | None
    ) -> IntentResult:
        """Gemma 상태 인지 분류 — 죽어 있던 `_SYSTEM_PROMPT`를 실제로 사용한다.

        대화 상태(확인 대기 draft 존재 여부)를 프롬프트에 주입해 draft↔refine을 가른다.
        LLM 실패/미상값은 상태 기반 안전 폴백(draft 있으면 refine).
        """
        safe_default = IntentType.REFINE if has_pending_draft else (fallback or IntentType.DRAFT)
        state_hint = (
            "현재 세션에는 사용자 확인(승인/수정)을 기다리는 워크플로우 초안이 이미 있습니다. "
            "따라서 노드·파라미터·연결을 바꾸거나 추가/삭제하거나 특정 값을 지정하는 발화는 "
            "기존 초안 수정이므로 'refine'입니다. 완전히 다른 새 자동화를 처음부터 요청할 때만 'draft'입니다."
            if has_pending_draft
            else "현재 세션에는 진행 중인 워크플로우 초안이 없습니다. 워크플로우 작성 요청은 'draft'입니다."
        )
        prompt = f"{_SYSTEM_PROMPT}\n[Session context]\n{state_hint}\n\n[User message]\n{user_message}"
        try:
            resp = await self._llm.generate_structured(prompt, _IntentLLMResponse)
        except Exception:
            return IntentResult(intent=safe_default, confidence=0.4, analyzed_entities={})

        intent = _coerce_intent(resp.intent) or safe_default
        return IntentResult(
            intent=intent,
            confidence=resp.confidence,
            analyzed_entities=resp.analyzed_entities or {},
        )
