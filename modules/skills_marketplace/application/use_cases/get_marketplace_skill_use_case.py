from __future__ import annotations

from uuid import UUID

from common_schemas.exceptions import NotFoundError, ValidationError

from ...domain.entities.marketplace_company_skill import MarketplaceCompanySkill
from ...domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from ...domain.ports.skill_repository import SkillRepository
from ...domain.value_objects.skill_scope import SkillScope
from ...domain.value_objects.skill_state import SkillState


class GetMarketplaceSkillUseCase:
    """마켓플레이스(team/company) 스킬 단건 조회 — browse 상세 페이지용.

    `ListMarketplaceSkillsUseCase`(목록)와 동일 정책: **PUBLISHED만 노출**한다(ADR-0020 (b)).
    미게시(draft/review/approved/archived) 스킬은 id를 직접 알아도 `NotFoundError`로 가린다 —
    존재 여부 자체를 숨겨 미검토 스킬의 name/description 열람을 차단(목록 라우트의 lifecycle 노출
    차단과 동일한 신뢰 경계).

    scope=PERSONAL은 owner 범위라 대상 아님(`GetPersonalSkillUseCase`가 owner 검사 수행) →
    `ValidationError`(→400).
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(
        self, scope: SkillScope, skill_id: UUID
    ) -> MarketplaceTeamSkill | MarketplaceCompanySkill:
        if scope == SkillScope.TEAM:
            skill = await self._repo.get_team(skill_id)
        elif scope == SkillScope.COMPANY:
            skill = await self._repo.get_company(skill_id)
        else:
            raise ValidationError("personal scope는 GET /api/v1/skills/personal/{id}를 사용하세요")

        # 미존재 + 미게시를 동일하게 404 — 미게시 스킬의 존재/메타 노출 차단(ADR-0020 (b)).
        if skill is None or SkillState(skill.lifecycle_state) != SkillState.PUBLISHED:
            raise NotFoundError(f"Marketplace {scope.value} skill {skill_id} not found")

        return skill
