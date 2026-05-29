from skills_marketplace.domain.services.promotion_service import PromotionService
from skills_marketplace.domain.value_objects.skill_scope import SkillScope


def test_can_promote_personal_to_team():
    assert PromotionService.can_promote(SkillScope.PERSONAL, SkillScope.TEAM) is True


def test_can_promote_team_to_company():
    assert PromotionService.can_promote(SkillScope.TEAM, SkillScope.COMPANY) is True


def test_cannot_promote_personal_to_company_skip():
    # 단계 건너뛰기 금지
    assert PromotionService.can_promote(SkillScope.PERSONAL, SkillScope.COMPANY) is False


def test_cannot_promote_backward():
    # 역방향 금지
    assert PromotionService.can_promote(SkillScope.TEAM, SkillScope.PERSONAL) is False
    assert PromotionService.can_promote(SkillScope.COMPANY, SkillScope.TEAM) is False


def test_cannot_promote_same_scope():
    assert PromotionService.can_promote(SkillScope.PERSONAL, SkillScope.PERSONAL) is False


def test_next_scope():
    assert PromotionService.next_scope(SkillScope.PERSONAL) == SkillScope.TEAM
    assert PromotionService.next_scope(SkillScope.TEAM) == SkillScope.COMPANY


def test_next_scope_company_is_terminal():
    # COMPANY는 최상위 — 다음 단계 없음
    assert PromotionService.next_scope(SkillScope.COMPANY) is None


def test_skill_scope_str_serialization():
    # str 상속 — JSON 직렬화 호환
    assert SkillScope.PERSONAL == "personal"
    assert SkillScope.TEAM.value == "team"
