"""복합 의도(레시피) 분류 순수 단위 테스트 (P3).

`classify_recipe` / `_is_skill_then_compose`는 정규식 기반 순수 함수 — LLM/IO 무관.
설계: docs/specs/plan/supervisor-loop-architecture.md §4.
"""
from __future__ import annotations

import pytest
from common_schemas.enums import IntentType

from ai_agent.domain.services.intent_analyzer_service import (
    _fast_classify,
    _is_skill_then_compose,
    classify_recipe,
)
from ai_agent.domain.value_objects.route_plan import RECIPE_SKILL_THEN_COMPOSE


class TestFastClassifyBuildSkill:
    """단일 build_skill 정규식 — 자연 발화 회귀(#496 e2e: '스킬 만들고 싶어' 미분류로 위저드 미발동)."""

    @pytest.mark.parametrize(
        "msg",
        [
            "나 스킬 만들고 싶어",     # 회귀 핵심 — '만들고'(어간 '만들')
            "스킬 만들어줘",
            "스킬 만들래",
            "스킬을 만들고 싶어",
            "스킬 하나 만들어줘",
            "스킬 좀 만들어볼래",
            "스킬 생성해줘",
            "스킬 제작하고 싶어",
            "skill 만들고 싶어",
        ],
    )
    def test_build_skill_natural_phrasings(self, msg: str) -> None:
        assert _fast_classify(msg) is IntentType.BUILD_SKILL

    @pytest.mark.parametrize(
        "msg",
        [
            "슬랙 알림 워크플로우 만들어줘",  # 스킬 신호 없음 → draft
            "이게 뭐야?",                     # 질문
            "안녕",                           # chitchat
        ],
    )
    def test_non_build_skill_not_misclassified(self, msg: str) -> None:
        assert _fast_classify(msg) is not IntentType.BUILD_SKILL


class TestIsSkillThenCompose:
    @pytest.mark.parametrize(
        "msg",
        [
            "보고서 작성 스킬 만들어서 매주 발송하는 워크플로우 만들어줘",
            "스킬 등록하고 그걸로 자동화 만들어줘",
            "이 SOP로 스킬 만든 다음 워크플로우로 연결해줘",
            "견적 스킬 빌드해서 자동화 플로우 구성해줘",
        ],
    )
    def test_composite_phrases_detected(self, msg: str) -> None:
        assert _is_skill_then_compose(msg) is True

    @pytest.mark.parametrize(
        "msg",
        [
            "스킬 만들어줘",  # compose 신호 없음
            "슬랙 알림 워크플로우 만들어줘",  # 스킬 신호 없음
            "스킬이랑 워크플로우 뭐가 달라?",  # 연결어 없음(질문)
            "안녕하세요",
        ],
    )
    def test_non_composite_phrases_rejected(self, msg: str) -> None:
        # 보수적 — 세 신호 동시 충족 아니면 복합 아님
        assert _is_skill_then_compose(msg) is False


class TestClassifyRecipe:
    def test_composite_overrides_base_intent(self) -> None:
        # base intent가 BUILD_SKILL이라도 복합 발화면 복합 키
        key = classify_recipe(
            "스킬 만들어서 워크플로우 만들어줘", IntentType.BUILD_SKILL
        )
        assert key == RECIPE_SKILL_THEN_COMPOSE

    @pytest.mark.parametrize(
        "intent,expected",
        [
            (IntentType.DRAFT, "draft"),
            (IntentType.BUILD_SKILL, "build_skill"),
            (IntentType.CHITCHAT, "chitchat"),
            (IntentType.PROPOSE, "propose"),
        ],
    )
    def test_single_intent_uses_intent_value(self, intent: IntentType, expected: str) -> None:
        # 단일 의도(복합 발화 아님) → intent.value 그대로
        assert classify_recipe("슬랙 알림 보내줘", intent) == expected

    def test_none_intent_non_composite_is_none(self) -> None:
        assert classify_recipe("음...", None) is None

    def test_none_intent_but_composite_still_keyed(self) -> None:
        # intent None이어도 복합 발화면 복합 키 (분류 독립)
        key = classify_recipe("스킬 만들어서 워크플로우 만들어줘", None)
        assert key == RECIPE_SKILL_THEN_COMPOSE
