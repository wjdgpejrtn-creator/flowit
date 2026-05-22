from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from skills_marketplace.domain.entities.approval_workflow import ApprovalWorkflow
from skills_marketplace.domain.entities.marketplace_company_skill import MarketplaceCompanySkill
from skills_marketplace.domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from skills_marketplace.domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from skills_marketplace.domain.ports.skill_repository import SkillRepository
from skills_marketplace.domain.value_objects.skill_scope import SkillScope
from skills_marketplace.domain.value_objects.skill_state import SkillState

from ..mappers.marketplace_skill_mapper import (
    CompanySkillMapper,
    PersonalSkillMapper,
    SkillApprovalMapper,
    TeamSkillMapper,
)
from ..orm.marketplace_skill_model import (
    CompanySkillModel,
    PersonalSkillModel,
    TeamSkillModel,
)


class PgMarketplaceSkillRepository(SkillRepository):
    """`SkillRepository`(3-scope ABC)의 PostgreSQL 구현체 — ADR-0020 ②.

    옛 `PgSkillRepository`(단일 `Skill` 모델)와 별개. 3계층 테이블
    (personal/team/company_skills) + skill_approvals를 다룬다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── save (upsert by PK) ──────────────────────────────────────────────────

    async def save_personal(self, skill: MarketplacePersonalSkill) -> MarketplacePersonalSkill:
        merged = await self._session.merge(PersonalSkillMapper.to_orm(skill))
        await self._session.flush()
        return PersonalSkillMapper.to_domain(merged)

    async def save_team(self, skill: MarketplaceTeamSkill) -> MarketplaceTeamSkill:
        merged = await self._session.merge(TeamSkillMapper.to_orm(skill))
        await self._session.flush()
        return TeamSkillMapper.to_domain(merged)

    async def save_company(self, skill: MarketplaceCompanySkill) -> MarketplaceCompanySkill:
        merged = await self._session.merge(CompanySkillMapper.to_orm(skill))
        await self._session.flush()
        return CompanySkillMapper.to_domain(merged)

    # ── get ──────────────────────────────────────────────────────────────────

    async def get_personal(self, skill_id: UUID) -> MarketplacePersonalSkill | None:
        model = await self._session.get(PersonalSkillModel, skill_id)
        return PersonalSkillMapper.to_domain(model) if model is not None else None

    async def get_team(self, skill_id: UUID) -> MarketplaceTeamSkill | None:
        model = await self._session.get(TeamSkillModel, skill_id)
        return TeamSkillMapper.to_domain(model) if model is not None else None

    async def get_company(self, skill_id: UUID) -> MarketplaceCompanySkill | None:
        model = await self._session.get(CompanySkillModel, skill_id)
        return CompanySkillMapper.to_domain(model) if model is not None else None

    # ── search ───────────────────────────────────────────────────────────────

    async def search(
        self,
        query_embedding: list[float],
        scope: SkillScope,
        limit: int = 10,
        include_promoted: bool = False,
        lifecycle_state: SkillState | None = None,
    ) -> list[MarketplacePersonalSkill | MarketplaceTeamSkill | MarketplaceCompanySkill]:
        # scope별 테이블 + 승격 마킹 컬럼 결정. company는 최상위라 promoted_to_* 없음.
        if scope == SkillScope.PERSONAL:
            model, mapper, promoted_col = (
                PersonalSkillModel, PersonalSkillMapper, PersonalSkillModel.promoted_to_team_id,
            )
        elif scope == SkillScope.TEAM:
            model, mapper, promoted_col = (
                TeamSkillModel, TeamSkillMapper, TeamSkillModel.promoted_to_company_id,
            )
        else:
            model, mapper, promoted_col = CompanySkillModel, CompanySkillMapper, None

        stmt = select(model).where(model.embedding.isnot(None))
        if lifecycle_state is not None:
            stmt = stmt.where(model.lifecycle_state == lifecycle_state.value)
        # include_promoted=False: 상위 scope로 승격된 원본 제외 (승격=복제, 중복 노출 방지)
        if not include_promoted and promoted_col is not None:
            stmt = stmt.where(promoted_col.is_(None))
        stmt = stmt.order_by(model.embedding.cosine_distance(query_embedding)).limit(limit)

        result = await self._session.execute(stmt)
        return [mapper.to_domain(row) for row in result.scalars().all()]

    # ── approval ─────────────────────────────────────────────────────────────

    async def save_approval(self, approval: ApprovalWorkflow) -> ApprovalWorkflow:
        merged = await self._session.merge(SkillApprovalMapper.to_orm(approval))
        await self._session.flush()
        return SkillApprovalMapper.to_domain(merged)
