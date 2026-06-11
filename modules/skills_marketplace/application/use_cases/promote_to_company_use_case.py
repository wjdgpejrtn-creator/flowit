from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from common_schemas.exceptions import NotFoundError, ValidationError

from ...domain.entities.marketplace_company_skill import MarketplaceCompanySkill
from ...domain.ports.skill_document_store import SkillDocumentStore
from ...domain.ports.skill_repository import SkillRepository
from ...domain.services.promotion_service import PromotionService
from ...domain.value_objects.skill_scope import SkillScope
from ...domain.value_objects.skill_state import SkillState


class PromoteToCompanyUseCase:
    """팀 스킬 → 전사 스킬 승격 (ADR-0012 v3 lifecycle, 승격=복제 정책).

    PromotionService로 TEAM → COMPANY 전이 검증 후 MarketplaceCompanySkill 생성.
    승격 = 복제(원본 유지) 정책 (조장 리뷰 #98):
    - 원본 team의 메타는 승계하되 게시상태는 DRAFT로 재심사 리셋
    - promoted_from으로 신규 company가 원본을 역추적
    - 원본 team에 promoted_to_company_id 마킹 → search(include_promoted=False) 기본 제외

    지침서(SKILL.md/COMPOSER.md)도 복제한다 — GCS 키가 skill_id에 결정적으로 묶여 있어
    `skill_document_uri` 문자열만 승계하면 신규 skill_id 경로에 객체가 없어 지침서 조회가 404가
    된다(PromoteToTeamUseCase와 동일). doc_store 미주입·원본 문서 없음 시에만 복사를 스킵하고,
    GCS I/O 실패는 전파해 승격을 중단한다(fail-closed — 지침서 없는 복사본 생성 방지).
    """

    def __init__(self, repo: SkillRepository, doc_store: SkillDocumentStore | None = None) -> None:
        self._repo = repo
        self._doc_store = doc_store

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
        # 지침서 GCS 객체를 신규 skill_id로 복제 — skill_document_uri는 복사본 경로로 갱신.
        document_uri = await self._copy_document(team.skill_id, new_skill_id, team.skill_document_uri)
        company_skill = MarketplaceCompanySkill(
            skill_id=new_skill_id,
            author_id=team.author_id,
            name=team.name,
            description=team.description,
            node_definition_id=team.node_definition_id,
            lifecycle_state=SkillState.DRAFT,        # 승격 = 재심사 리셋 (게시상태 비승계, 조장 리뷰 #98)
            skill_document_uri=document_uri,
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
        # 승격 = 복제(원본 유지) — 원본 team에 promoted_to 마킹 → 검색 기본 제외
        await self._repo.save_team(
            team.model_copy(update={"promoted_to_company_id": new_skill_id, "updated_at": now})
        )
        return new_skill_id

    async def _copy_document(self, src_skill_id: UUID, dst_skill_id: UUID, fallback_uri: str | None) -> str | None:
        """원본 skill_id의 지침서를 신규 skill_id로 GCS 복제하고 새 URI 반환.

        복사 대상이 없을 때만(doc_store 미주입 / 원본 문서 없음) fallback_uri를 반환한다. GCS I/O
        예외는 잡지 않고 전파해 승격을 중단한다(fail-closed — 지침서 없는 복사본 생성 방지).
        """
        if self._doc_store is None:
            return fallback_uri
        document = await self._doc_store.load(src_skill_id)
        if document is None:
            return fallback_uri
        return await self._doc_store.save(dst_skill_id, document)
