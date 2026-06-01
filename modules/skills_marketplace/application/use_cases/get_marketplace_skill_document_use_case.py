from __future__ import annotations

from uuid import UUID

from common_schemas import SkillDocument
from common_schemas.exceptions import NotFoundError, ValidationError

from ...domain.ports.skill_document_store import SkillDocumentStore
from ...domain.ports.skill_repository import SkillRepository
from ...domain.value_objects.skill_scope import SkillScope
from ...domain.value_objects.skill_state import SkillState


class GetMarketplaceSkillDocumentUseCase:
    """마켓플레이스(team/company) 스킬의 지침서(SkillDocument/SKILL.md) 조회 — 상세 페이지 본문.

    `GetMarketplaceSkillUseCase`(메타)와 동일 신뢰 경계로 **PUBLISHED만** 노출한다(ADR-0020 (b)):
    미존재/미게시 스킬은 `NotFoundError`(→404)로 가려 id 직접 접근으로 미검토 스킬의 지침서를
    읽는 것을 차단한다. 게이트 통과 후 GCS(`SkillDocumentStore.load`)에서 SKILL.md를 읽어 반환.

    메타 조회(`SkillRepository`)와 지침서 조회(`SkillDocumentStore`)를 한 use case로 조합 —
    ADR-0017 이중 저장의 두 측을 lifecycle 게이트로 묶는다. 지침서가 없으면(예: 수동 생성 스킬,
    GCS 미저장) `NotFoundError`로 "지침서 없음"을 표현(라우터가 404 → 프론트 graceful).

    scope=PERSONAL은 owner 범위라 대상 아님(`ValidationError`→400).
    """

    def __init__(self, repo: SkillRepository, doc_store: SkillDocumentStore) -> None:
        self._repo = repo
        self._doc_store = doc_store

    async def execute(self, scope: SkillScope, skill_id: UUID) -> SkillDocument:
        if scope == SkillScope.TEAM:
            skill = await self._repo.get_team(skill_id)
        elif scope == SkillScope.COMPANY:
            skill = await self._repo.get_company(skill_id)
        else:
            raise ValidationError("personal scope는 마켓플레이스 지침서 조회 대상이 아닙니다")

        # 미존재 + 미게시를 동일 404 — 미게시 스킬의 지침서 노출 차단(메타 조회와 동일 경계).
        if skill is None or SkillState(skill.lifecycle_state) != SkillState.PUBLISHED:
            raise NotFoundError(f"Marketplace {scope.value} skill {skill_id} not found")

        document = await self._doc_store.load(skill_id)
        if document is None:
            raise NotFoundError(f"Skill {skill_id} has no document")

        return document
