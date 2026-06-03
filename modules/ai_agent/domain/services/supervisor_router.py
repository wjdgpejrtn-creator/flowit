"""Supervisor 라우팅 — 결정형 라우터 (LLM 아님, 순수 도메인 서비스).

설계: docs/specs/plan/supervisor-loop-architecture.md §3, §6.

의도 분류(LLM 가능)는 intent_node에서 끝나고, 거기서 나온 **레시피 키**로
RECIPES를 조회해 forward 스텝 큐(RoutePlan)를 만든다. 라우팅 자체는 LLM이
관여하지 않으므로 재현 가능·순수 단위 테스트 가능하다.
"""
from __future__ import annotations

from common_schemas.handoff import HandoffPayload

from ..value_objects.route_plan import (
    RECIPE_SKILL_THEN_COMPOSE,
    RoutePlan,
    RouteTarget,
)

# 미분류 입력(intent=None)용 레시피 키.
UNCLASSIFIED = "__unclassified__"

# 루프 무한 방어 — 전체 홉 상한 (langgraph recursion_limit 전례 교훈).
MAX_HOPS = 8

# 단일 target relay 실패 시 재시도 한도 (recovery_mode).
MAX_RETRIES = 1

# 레시피 = 레시피 키 → forward 스텝 시퀀스.
# 단일 의도는 IntentType.value를 키로, 복합 의도만 별도 키.
RECIPES: dict[str, list[RouteTarget]] = {
    "chitchat": [RouteTarget.FAST_RESPONSE],
    "info_question": [RouteTarget.FAST_RESPONSE],
    "control": [RouteTarget.FAST_RESPONSE],
    "workflow_execute": [RouteTarget.FAST_RESPONSE],
    "propose": [RouteTarget.FINALIZE],
    "draft": [RouteTarget.COMPOSER],
    "refine": [RouteTarget.COMPOSER],
    "clarify": [RouteTarget.COMPOSER],
    "build_skill": [RouteTarget.SKILLS],
    # ── 복합 레시피 (화이트리스트만, 동적 체이닝 제외) ──
    # 스킬을 만들고 그 스킬로 곧장 워크플로우 작성. SKILLS가 selected_skill_id를
    # state에 write → COMPOSER가 read (state-mediated, §5).
    RECIPE_SKILL_THEN_COMPOSE: [RouteTarget.SKILLS, RouteTarget.COMPOSER],
    UNCLASSIFIED: [RouteTarget.GENERAL_CHAT],
}


def make_plan(recipe_key: str | None) -> RoutePlan:
    """레시피 키 → RoutePlan. 미등록/None 키는 미분류(general_chat)로 폴백."""
    key = recipe_key or UNCLASSIFIED
    steps = RECIPES.get(key)
    if steps is None:
        key = UNCLASSIFIED
        steps = RECIPES[UNCLASSIFIED]
    return RoutePlan(recipe_key=key, steps=list(steps))


def route(plan: RoutePlan) -> RouteTarget:
    """순수 함수: plan 커서가 가리키는 다음 forward 스텝. 끝이면 DONE.

    LLM 관여 없음 — 레시피 큐만 소비한다.
    """
    return plan.peek() or RouteTarget.DONE


def recovery_target(
    plan: RoutePlan,
    handoff: HandoffPayload,
    retry_count: int,
) -> RouteTarget | None:
    """순수 함수: 실패 핸드오프 → 복구 라우팅. None이면 포기(ErrorFrame).

    - ``recovery_mode``: 재시도 한도 내면 동일 target 재시도, 초과면 None
    - ``result_review``: composer로 보정 라우팅 (부분 결과 검토)
    - 무한루프 위험 코드(E_RELAY_LIMIT)는 즉시 포기

    retry_count는 supervisor 루프가 _State에 누적해 주입한다 (순수성 유지).
    """
    if "E_RELAY_LIMIT" in handoff.error_codes:
        return None
    if handoff.handoff_type == "recovery_mode":
        if retry_count >= MAX_RETRIES:
            return None
        return plan.peek()  # 커서 미전진 → 동일 target 재시도
    if handoff.handoff_type == "result_review":
        return RouteTarget.COMPOSER
    return None
