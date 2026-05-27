from __future__ import annotations

from uuid import UUID

from common_schemas.exceptions import AuthorizationError, NotFoundError, ValidationError

from ...domain.ports.skill_document_store import SkillDocumentStore
from ...domain.ports.skill_repository import SkillRepository
from ...domain.value_objects.skill_state import SkillState


class DeletePersonalSkillUseCase:
    """개인 스킬 삭제 — personal skills 편집 UI (REQ-013, 가원 요청).

    api_server `DELETE /skills/personal/{id}` 라우트가 조립. 신뢰 경계:

    - 인가: **owner만**(`actor_user_id == owner_user_id`) — 아니면 `AuthorizationError`(fail-closed).
    - lifecycle: **DRAFT 상태만** 삭제 — published/approved는 NodeDefinition 연결/타인 참조 가능성이 있어 보호.

    ADR-0017 이중 저장 정리: `doc_store` 주입 시 GCS의 `SKILL.md`도 함께 삭제(2026-05-26 조장 결정).
    DB row보다 **GCS를 먼저** 삭제 — GCS 삭제 실패 시 DB row가 남아 재시도 가능(역방향이면 orphan 잔존).
    `doc_store.delete`는 멱등(객체 없으면 no-op)이라 `skill_document_uri`가 없거나 이미 지워졌어도 안전.
    `doc_store` 미주입 시(테스트/문서 없는 경로) DB row만 삭제.
    """

    _DELETABLE_STATE = SkillState.DRAFT

    def __init__(self, repo: SkillRepository, doc_store: SkillDocumentStore | None = None) -> None:
        self._repo = repo
        self._doc_store = doc_store

    async def execute(self, skill_id: UUID, actor_user_id: UUID) -> None:
        skill = await self._repo.get_personal(skill_id)
        if skill is None:
            raise NotFoundError(f"Personal skill {skill_id} not found")

        if skill.owner_user_id != actor_user_id:
            raise AuthorizationError(
                f"User {actor_user_id} is not the owner of personal skill {skill_id}"
            )

        if SkillState(skill.lifecycle_state) != self._DELETABLE_STATE:
            raise ValidationError(
                f"Personal skill {skill_id} is '{skill.lifecycle_state}' — only DRAFT skills are deletable"
            )

        # GCS SkillDocument 먼저 정리(주입 + 문서 존재 시) — orphan 방지, 멱등.
        if self._doc_store is not None and skill.skill_document_uri:
            await self._doc_store.delete(skill_id)

        await self._repo.delete_personal(skill_id)
