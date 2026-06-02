from __future__ import annotations

from itertools import zip_longest
from uuid import UUID

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
        owner_user_id: UUID | None = None,
        max_distance: float | None = None,
    ) -> list[SkillResult]:
        """scope 범위 내 query_embedding 유사도 top-k 스킬 후보 반환.

        lifecycle_state 기본 PUBLISHED (ADR-0020 (b)): Composer 후보는 게시된 스킬만 노출.
        관리/디버그 목적이면 None을 명시해 전체 상태 검색.

        owner_user_id: scope=PERSONAL일 때 소유자 인가 필터(미지정 시 개인 스킬 빈 결과 — IDOR 차단).
        max_distance: 코사인 거리 상한(관련성 컷). None이면 거리 필터 없이 top-k.
        """
        return await self._repo.search(
            query_embedding,
            scope,
            limit,
            lifecycle_state=lifecycle_state,
            owner_user_id=owner_user_id,
            max_distance=max_distance,
        )

    async def execute_accessible(
        self,
        query_embedding: list[float],
        user_id: UUID,
        limit: int = 5,
        lifecycle_state: SkillState | None = SkillState.PUBLISHED,
        max_distance: float | None = None,
    ) -> list[SkillResult]:
        """호출자가 접근 가능한 스코프(개인 본인 + 전사)를 함께 검색해 유사도 순으로 병합.

        Composer가 회사 스킬만 보던 한계를 보완 — personal(owner=user_id) + company를 각각
        관련성 컷(max_distance) 적용해 검색한 뒤 합쳐 상위 `limit`개를 돌려준다. 팀(team) 스코프는
        팀 식별자가 Composer까지 전달되면 후속 추가(현재 protocol 미전달).

        병합 정렬: repo.search가 거리값을 반환하지 않으므로 scope별 거리순 결과를 라운드로빈으로
        섞어 어느 한 스코프가 목록을 독점하지 않게 한다(둘 다 max_distance 컷을 통과한 관련 후보).
        skill_id 기준 중복 제거.
        """
        personal = await self._repo.search(
            query_embedding,
            SkillScope.PERSONAL,
            limit,
            lifecycle_state=lifecycle_state,
            owner_user_id=user_id,
            max_distance=max_distance,
        )
        company = await self._repo.search(
            query_embedding,
            SkillScope.COMPANY,
            limit,
            lifecycle_state=lifecycle_state,
            max_distance=max_distance,
        )

        merged: list[SkillResult] = []
        seen: set[UUID] = set()
        for personal_skill, company_skill in zip_longest(personal, company):
            for candidate in (personal_skill, company_skill):
                if candidate is None:
                    continue
                skill_id = getattr(candidate, "skill_id", None)
                if skill_id is not None and skill_id in seen:
                    continue
                if skill_id is not None:
                    seen.add(skill_id)
                merged.append(candidate)
                if len(merged) >= limit:
                    return merged
        return merged
