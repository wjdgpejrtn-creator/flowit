"""supervisor_router + RoutePlan 순수 도메인 단위 테스트 (P0).

설계: docs/specs/plan/supervisor-loop-architecture.md §3, §6.
mock 불필요 — LLM/IO 의존 없는 순수 함수만 검증.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas.handoff import HandoffPayload

from ai_agent.domain.services.supervisor_router import (
    MAX_RETRIES,
    RECIPES,
    UNCLASSIFIED,
    make_plan,
    recovery_target,
    route,
)
from ai_agent.domain.value_objects.route_plan import RoutePlan, RouteTarget


def _handoff(handoff_type: str, error_codes: list[str] | None = None) -> HandoffPayload:
    return HandoffPayload(
        handoff_type=handoff_type,  # type: ignore[arg-type]
        direction="reverse",
        error_codes=error_codes or [],
        error_messages=[],
        state_data={},
        correlation_id=uuid4(),
    )


# ── RoutePlan ────────────────────────────────────────────────────────────────


class TestRoutePlan:
    def test_peek_advance_until_done(self) -> None:
        plan = RoutePlan(recipe_key="skill_then_compose", steps=[RouteTarget.SKILLS, RouteTarget.COMPOSER])
        assert plan.peek() == RouteTarget.SKILLS
        plan.advance()
        assert plan.peek() == RouteTarget.COMPOSER
        plan.advance()
        assert plan.peek() is None
        assert plan.is_done()

    def test_peek_does_not_advance(self) -> None:
        plan = RoutePlan(recipe_key="draft", steps=[RouteTarget.COMPOSER])
        assert plan.peek() == RouteTarget.COMPOSER
        assert plan.peek() == RouteTarget.COMPOSER  # 멱등
        assert plan.cursor == 0

    def test_insert_at_cursor_is_next_peek(self) -> None:
        plan = RoutePlan(recipe_key="draft", steps=[RouteTarget.COMPOSER])
        plan.insert(RouteTarget.COMPOSER)  # 재시도용 대체 스텝
        assert plan.peek() == RouteTarget.COMPOSER
        assert plan.remaining() == [RouteTarget.COMPOSER, RouteTarget.COMPOSER]

    def test_remaining_reflects_cursor(self) -> None:
        plan = RoutePlan(recipe_key="skill_then_compose", steps=[RouteTarget.SKILLS, RouteTarget.COMPOSER])
        plan.advance()
        assert plan.remaining() == [RouteTarget.COMPOSER]

    def test_empty_plan_is_done(self) -> None:
        plan = RoutePlan(recipe_key="x", steps=[])
        assert plan.peek() is None
        assert plan.is_done()


# ── make_plan ────────────────────────────────────────────────────────────────


class TestMakePlan:
    @pytest.mark.parametrize(
        "key,expected",
        [
            ("draft", [RouteTarget.COMPOSER]),
            ("chitchat", [RouteTarget.FAST_RESPONSE]),
            ("propose", [RouteTarget.FINALIZE]),
            ("build_skill", [RouteTarget.SKILLS]),
            ("skill_then_compose", [RouteTarget.SKILLS, RouteTarget.COMPOSER]),
        ],
    )
    def test_known_keys(self, key: str, expected: list[RouteTarget]) -> None:
        assert make_plan(key).steps == expected

    def test_none_key_falls_back_to_unclassified(self) -> None:
        plan = make_plan(None)
        assert plan.recipe_key == UNCLASSIFIED
        assert plan.steps == [RouteTarget.GENERAL_CHAT]

    def test_unknown_key_falls_back_to_unclassified(self) -> None:
        plan = make_plan("bogus_recipe")
        assert plan.recipe_key == UNCLASSIFIED
        assert plan.steps == [RouteTarget.GENERAL_CHAT]

    def test_plan_steps_are_copy_not_shared(self) -> None:
        # 한 plan의 insert가 RECIPES 원본을 오염시키면 안 됨
        plan = make_plan("draft")
        plan.insert(RouteTarget.COMPOSER)
        assert RECIPES["draft"] == [RouteTarget.COMPOSER]


# ── route ────────────────────────────────────────────────────────────────────


class TestRoute:
    def test_route_returns_current_step(self) -> None:
        plan = make_plan("skill_then_compose")
        assert route(plan) == RouteTarget.SKILLS
        plan.advance()
        assert route(plan) == RouteTarget.COMPOSER

    def test_route_returns_done_when_exhausted(self) -> None:
        plan = make_plan("draft")
        plan.advance()
        assert route(plan) == RouteTarget.DONE


# ── recovery_target ──────────────────────────────────────────────────────────


class TestRecoveryTarget:
    def test_recovery_mode_retries_same_target_within_limit(self) -> None:
        plan = make_plan("draft")  # peek == COMPOSER
        target = recovery_target(plan, _handoff("recovery_mode"), retry_count=0)
        assert target == RouteTarget.COMPOSER

    def test_recovery_mode_gives_up_over_limit(self) -> None:
        plan = make_plan("draft")
        target = recovery_target(plan, _handoff("recovery_mode"), retry_count=MAX_RETRIES)
        assert target is None

    def test_relay_limit_code_gives_up_immediately(self) -> None:
        plan = make_plan("draft")
        target = recovery_target(
            plan, _handoff("recovery_mode", error_codes=["E_RELAY_LIMIT"]), retry_count=0
        )
        assert target is None

    def test_result_review_routes_to_composer(self) -> None:
        plan = make_plan("build_skill")
        target = recovery_target(plan, _handoff("result_review"), retry_count=0)
        assert target == RouteTarget.COMPOSER
