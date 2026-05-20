from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from common_schemas.exceptions import NotFoundError, ValidationError

from ...domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.promotion_service import PromotionService
from ...domain.value_objects.skill_scope import SkillScope


class PromoteToTeamUseCase:
    """개인 스킬 → 팀 스킬 승격 (ADR-0012 v3 lifecycle).

    PromotionService로 PERSONAL → TEAM 전이 검증 후 MarketplaceTeamSkill 생성.
    원본 personal skill의 메타/게시상태를 승계하고 promoted_from으로 추적.
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(self, personal_skill_id: UUID, team_id: UUID) -> UUID:
        """개인 스킬을 팀 범위로 승격하고 신규 team skill_id 반환."""
        personal = await self._repo.get_personal(personal_skill_id)
        if personal is None:
            raise NotFoundError(f"MarketplacePersonalSkill {personal_skill_id} not found")

        if not PromotionService.can_promote(SkillScope.PERSONAL, SkillScope.TEAM):
            raise ValidationError(
                f"Cannot promote {SkillScope.PERSONAL.value} → {SkillScope.TEAM.value}",
                code="E-SKILL-PROMOTE-001",
            )

        now = datetime.now(UTC)
        new_skill_id = uuid4()
        team_skill = MarketplaceTeamSkill(
            skill_id=new_skill_id,
            team_id=team_id,
            author_id=personal.owner_user_id,
            name=personal.name,
            description=personal.description,
            node_definition_id=personal.node_definition_id,
            lifecycle_state=personal.lifecycle_state,
            skill_document_uri=personal.skill_document_uri,
            embedding=personal.embedding,
            workflow_id=personal.workflow_id,
            tags=list(personal.tags),
            version=personal.version,
            metadata=dict(personal.metadata),
            promoted_from=personal_skill_id,
            created_at=now,
            updated_at=now,
        )
        await self._repo.save_team(team_skill)
        return new_skill_id
