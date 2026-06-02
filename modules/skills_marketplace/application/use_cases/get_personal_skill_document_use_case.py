from __future__ import annotations

from uuid import UUID

from common_schemas import SkillDocument
from common_schemas.exceptions import AuthorizationError, NotFoundError

from ...domain.ports.skill_document_store import SkillDocumentStore
from ...domain.ports.skill_repository import SkillRepository


class GetPersonalSkillDocumentUseCase:
    """개인 스킬의 지침서(SkillDocument/SKILL.md) 조회 — personal 상세 페이지 본문 (REQ-013).

    `GetPersonalSkillUseCase`(메타)와 동일 신뢰 경계지만 본문은 GCS에서 읽는다:

    - 인가: **owner만**(`actor_user_id == owner_user_id`) — 아니면 `AuthorizationError`(fail-closed).
      `GetMarketplaceSkillDocumentUseCase`는 PUBLISHED만 노출하지만(공개 browse), personal은
      owner 본인의 미게시 DRAFT 본문을 미리보기·편집해야 하므로 **lifecycle 게이트 없이** owner
      게이트만 적용한다.
    - 메타 조회(`SkillRepository`)로 owner 게이트를 통과한 뒤 GCS(`SkillDocumentStore.load`)에서
      SKILL.md를 읽는다. 지침서가 없으면(수동 생성/미저장) `NotFoundError`로 "지침서 없음"을 표현
      (라우터가 404 → 프론트 graceful "등록된 지침서 없음").
    """

    def __init__(self, repo: SkillRepository, doc_store: SkillDocumentStore) -> None:
        self._repo = repo
        self._doc_store = doc_store

    async def execute(self, skill_id: UUID, actor_user_id: UUID) -> SkillDocument:
        skill = await self._repo.get_personal(skill_id)
        if skill is None:
            raise NotFoundError(f"Personal skill {skill_id} not found")

        if skill.owner_user_id != actor_user_id:
            raise AuthorizationError(
                f"User {actor_user_id} is not the owner of personal skill {skill_id}"
            )

        document = await self._doc_store.load(skill_id)
        if document is None:
            raise NotFoundError(f"Skill {skill_id} has no document")

        return document
