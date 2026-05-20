from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from common_schemas.exceptions import NotFoundError, ValidationError

from ...domain.entities.marketplace_company_skill import MarketplaceCompanySkill
from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.promotion_service import PromotionService
from ...domain.value_objects.skill_scope import SkillScope


class PromoteToCompanyUseCase:
    """팀 스킬 → 전사 스킬 승격 (ADR-0012 v3 lifecycle).

    PromotionService로 TEAM → COMPANY 전이 검증 후 MarketplaceCompanySkill 생성.
    원본 team skill의 메타/게시상태를 승계하고 promoted_from으로 추적.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(self, team_skill_id: UUID) -> UUID:
        """팀 스킬을 전사 범위로 승격하고 신규 company skill_id 반환."""
        team = await self._repo.get_team(team_skill_id)
        if team is None:
            raise NotFoundError(f"MarketplaceTeamSkill {team_skill_id} not found")

        if not PromotionService.can_promote(SkillScope.TEAM, SkillScope.COMPANY):
            raise ValidationError(
                f"Cannot promote {SkillScope.TEAM.value} → {SkillScope.COMPANY.value}",
                code="E-SKILL-PROMOTE-002",
            )

        now = datetime.now(UTC)
        new_skill_id = uuid4()
        company_skill = MarketplaceCompanySkill(
            skill_id=new_skill_id,
            author_id=team.author_id,
            name=team.name,
            description=team.description,
            node_definition_id=team.node_definition_id,
            lifecycle_state=team.lifecycle_state,
            skill_document_uri=team.skill_document_uri,
            embedding=team.embedding,
            workflow_id=team.workflow_id,
            tags=list(team.tags),
            version=team.version,
            metadata=dict(team.metadata),
            promoted_from=team_skill_id,
            created_at=now,
            updated_at=now,
        )
        await self._repo.save_company(company_skill)
        return new_skill_id
