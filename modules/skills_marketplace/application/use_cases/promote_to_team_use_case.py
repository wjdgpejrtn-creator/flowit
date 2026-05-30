from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from common_schemas.exceptions import NotFoundError, ValidationError

from ...domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.promotion_service import PromotionService
from ...domain.value_objects.skill_scope import SkillScope
from ...domain.value_objects.skill_state import SkillState


class PromoteToTeamUseCase:
    """개인 스킬 → 팀 스킬 승격 (ADR-0012 v3 lifecycle, 승격=복제 정책).

    PromotionService로 PERSONAL → TEAM 전이 검증 후 MarketplaceTeamSkill 생성.
    승격 = 복제(원본 유지) 정책 (조장 리뷰 #98):
    - 원본 personal의 메타는 승계하되 게시상태는 DRAFT로 재심사 리셋 (넓은 scope = 재승인 경유)
    - promoted_from으로 신규 team이 원본을 역추적
    - 원본 personal에 promoted_to_team_id 마킹 → search(include_promoted=False) 기본 제외 (중복 노출 방지)
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
            lifecycle_state=SkillState.DRAFT,        # 승격 = 재심사 리셋 (게시상태 비승계, 조장 리뷰 #98)
            skill_document_uri=personal.skill_document_uri,
            embedding=personal.embedding,
            workflow_id=personal.workflow_id,
            tags=list(personal.tags),
            version=personal.version,
            metadata=dict(personal.metadata),
            # source_document_id(REQ-010 문서 association)는 personal 전용 — 승격=복제 시 의도적 비승계.
            # MarketplaceTeamSkill에 해당 필드가 없어 구조적으로도 복사되지 않는다(필드 단위 명시 생성).
            promoted_from=personal_skill_id,
            created_at=now,
            updated_at=now,
        )
        await self._repo.save_team(team_skill)
        # 승격 = 복제(원본 유지) — 원본 personal에 promoted_to 마킹 → 검색 기본 제외 (중복 노출 방지)
        await self._repo.save_personal(
            personal.model_copy(update={"promoted_to_team_id": new_skill_id, "updated_at": now})
        )
        return new_skill_id
