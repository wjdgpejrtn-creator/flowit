from __future__ import annotations

import logging
import re
from typing import Any, Literal

from common_schemas import IntentResult
from common_schemas.enums import IntentType
from pydantic import BaseModel

from ..ports.llm_port import LLMPort
from ..value_objects.route_plan import RECIPE_SKILL_THEN_COMPOSE

_logger = logging.getLogger(__name__)

# ── 키워드 기반 fallback classifier ──────────────────────────────────────────
# 1차 분류는 Gemma 4(LLM)가 한다 — 자연어는 규칙 몇 개로 분류 불가(예: "만들어"는 잡고
# "만들고 싶어"는 놓침). 아래 정규식은 **llm-base 다운/타임아웃 시 비상 fallback 전용**이다.

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
# 정규식은 fallback 전용(주 분류는 Gemma). "만들어"만 잡으면 "스킬 만들고 싶어"·"스킬 만들래"를
# 놓치니 어간 "만들"로 넓히고 생성/제작 동의어 + 을/를/하나/좀/새 필러를 허용한다. 복합용
# _SKILL_SIGNAL_RE와 **동의어·필러까지 동일**하게 유지(어긋나면 단일↔복합 분류 비일관).
_BUILD_SKILL_RE = re.compile(
    r"(스킬|skill)\s*(을|를|좀|하나|새|한\s*개)?\s*(만들|만든|빌드|build|등록|추가|생성|제작|디자인)",
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
# 단일 _BUILD_SKILL_RE와 **동의어·필러까지 동일**하게 유지 — 어긋나면 "스킬 제작해서 워크플로우"가
# 단일은 잡고 복합은 놓치는 비일관 발생(복합은 regex 전용이라 정렬이 특히 중요).
_SKILL_SIGNAL_RE = re.compile(
    r"(스킬|skill)\s*(을|를|좀|하나|새|한\s*개)?\s*(만들|만든|빌드|build|등록|추가|생성|제작|디자인)",
    re.IGNORECASE,
)
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


# draft/refine는 **상태 의존** 의도 — 같은 발화도 세션에 확인 대기 draft가 있는지에 따라
# 정답이 갈린다("채널 #general로 해줘" = draft無→새 생성 / draft有→수정). 정규식 표면만으론
# 못 가르므로, 호출부가 `has_pending_draft`를 주면 **편집 잠금**(draft 존재 시 결정적 refine
# 고정)으로 해소한다(#369). draft↔refine을 Gemma로 가르던 경로는 작은 모델 오분류로 편집이
# 새 생성으로 새던 회귀 때문에 제거됨.
_STATEFUL_INTENTS = frozenset({IntentType.DRAFT, IntentType.REFINE})


# ── Gemma 4 1차 의도 분류 ─────────────────────────────────────────────────────
# clarify는 사용자 입력 의도가 아니라 에이전트 상태 의도라 분류 대상에서 제외(8종).


class _IntentClassification(BaseModel):
    """Gemma 1차 분류 결과 — generate_structured 스키마(JSON 제약 출력)."""

    intent: Literal[
        "build_skill",
        "draft",
        "refine",
        "propose",
        "chitchat",
        "info_question",
        "control",
        "workflow_execute",
    ]


_CLASSIFY_PROMPT = """당신은 업무 자동화 어시스턴트의 의도 분류기입니다.
사용자의 마지막 발화를 아래 의도 중 정확히 하나로 분류해 JSON으로 답하세요.

- build_skill: 재사용 가능한 '스킬'을 만들거나 등록하고 싶다. 예: "스킬 만들고 싶어", "이 문서로 스킬 만들어줘"
- draft: 새 워크플로우/자동화를 만들어 달라. 예: "매주 월요일 시트 읽어서 슬랙으로 보내줘", "슬랙 알림 자동화 만들어줘"
- refine: 방금 만든 워크플로우를 수정/변경. 예: "채널을 #general로 바꿔줘", "그 노드 빼줘"
- propose: 제안된 워크플로우를 이대로 승인/확정. 예: "이대로 진행해줘", "좋아 승인"
- chitchat: 인사·잡담·감사. 예: "안녕", "고마워", "수고했어"
- info_question: 기능·사용법 질문. 예: "이게 뭐야?", "어떻게 사용해?", "뭘 할 수 있어?"
- control: 취소·초기화·중단. 예: "취소", "처음부터 다시", "리셋"
- workflow_execute: 지금 바로 실행. 예: "실행해줘", "바로 실행"

발화: "{message}"
"""


class IntentAnalyzerService:
    def __init__(self, llm: LLMPort) -> None:
        # 1차 의도 분류는 Gemma 4(`self._llm`)가 수행한다 — 이 에이전트들을 Gemma로 만든 이유가
        # 자연어 이해다. 정규식은 llm-base 다운 시 비상 fallback 전용. draft↔refine은 텍스트로
        # 못 푸는 **세션 상태 의존** 축이라 Gemma가 아니라 편집 잠금(has_pending_draft)으로 푼다.
        self._llm = llm

    async def _classify_with_llm(self, message: str) -> IntentType | None:
        """Gemma 4로 1차 의도 분류. 실패(llm-base 다운/타임아웃/파싱)면 None → 정규식 fallback."""
        text = message.strip()
        if not text:
            return None
        try:
            out = await self._llm.generate_structured(
                _CLASSIFY_PROMPT.format(message=text),
                _IntentClassification,
                max_tokens=24,
            )
            return IntentType(out.intent)
        except Exception as exc:  # llm-base 다운/타임아웃/스키마 위반 — 정규식으로 폴백
            _logger.warning("intent LLM 분류 실패 — 정규식 fallback: %s", exc)
            return None

    async def analyze(self, messages: list[dict[str, Any]], context: dict[str, Any]) -> IntentResult | None:
        user_message = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_message = m.get("content", "")
                break

        # 1차 의도 분류 — Gemma 4가 자연어를 이해해 분류(주). llm-base 다운/타임아웃 시에만 정규식
        # fallback. (정규식 단독은 "스킬 만들고 싶어" 같은 표현 변주를 못 잡아 위저드 미발동 회귀.)
        base_intent = await self._classify_with_llm(user_message)
        if base_intent is None:
            base_intent = _fast_classify(user_message)

        # 무상태·명시적 의도(제어/실행/인사/승인/안내/스킬빌드)는 세션 상태와 무관 — 편집 잠금 단락.
        if base_intent is not None and base_intent not in _STATEFUL_INTENTS:
            return IntentResult(intent=base_intent, confidence=0.9, analyzed_entities={})

        # 여기 도달 = draft/refine/미분류 = '워크플로우 구성' 의도(상태 의존).
        has_draft = context.get("has_pending_draft")
        if has_draft is not None:
            # 핵심 불변식: refine은 확인 대기 draft가 있어야만 성립한다.
            if has_draft:
                # **편집 잠금(#369)**: 확인 대기 draft가 있으면 이 세션은 편집 모드다. draft/refine/
                # 미분류 발화는 전부 기존 draft 수정(refine)으로 **결정적 확정** — 새 워크플로우
                # 생성을 잠근다(새로 만들려면 "새 대화"로 세션 초기화). 세션 상태는 텍스트로 못 푸는
                # 축이라 LLM이 아니라 상태로 푼다(Gemma 분류의 보완재 — 둘은 상호 배타가 아님).
                return IntentResult(intent=IntentType.REFINE, confidence=1.0, analyzed_entities={})
            # draft 없음 → refine 불가능 → refine 오탐은 새 생성(draft)으로 교정한다.
            if base_intent is IntentType.REFINE:
                base_intent = IntentType.DRAFT

        # 무상태 호출부(supervisor)이거나 draft 없는 경우 — 분류 결과 그대로.
        # supervisor는 draft/refine이 동일 레시피(→COMPOSER)라 둘 중 무엇이어도 충분하다.
        if base_intent is not None:
            return IntentResult(intent=base_intent, confidence=0.9, analyzed_entities={})
        return None
