from __future__ import annotations

from ...domain.entities.marketplace_company_skill import MarketplaceCompanySkill
from ...domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from ...domain.entities.marketplace_team_skill import MarketplaceTeamSkill
from ...domain.ports.skill_repository import SkillRepository
from ...domain.value_objects.skill_scope import SkillScope
from ...domain.value_objects.skill_state import SkillState

SkillResult = MarketplacePersonalSkill | MarketplaceTeamSkill | MarketplaceCompanySkill


class SearchSkillsUseCase:
    """하이브리드 스킬 검색 — ai_agent Workflow Composer가 호출 (ADR-0017 §Composer 검색 흐름).

    사용자 의도(intent) 파악 후 노드 탐색 타이밍에 스킬도 동시 탐색해서 유사 후보를 옵션 제시
    (CLAUDE.md L148 `ai_agent → skills_marketplace.application.use_cases`).

    embedding 생성은 호출측(Composer, EmbedderPort)이 담당하고, 본 use case는 query_embedding을
    받아 repo.search에 위임한다 (하이브리드 검색 구현은 SkillRepository 어댑터 — storage PR-2d).
    """

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        query_embedding: list[float],
        scope: SkillScope = SkillScope.COMPANY,
        limit: int = 10,
        lifecycle_state: SkillState | None = SkillState.PUBLISHED,
    ) -> list[SkillResult]:
        """scope 범위 내 query_embedding 유사도 top-k 스킬 후보 반환.

        lifecycle_state 기본 PUBLISHED (ADR-0020 (b)): Composer 후보는 게시된 스킬만 노출.
        관리/디버그 목적이면 None을 명시해 전체 상태 검색.
        """
        return await self._repo.search(
            query_embedding, scope, limit, lifecycle_state=lifecycle_state
        )
