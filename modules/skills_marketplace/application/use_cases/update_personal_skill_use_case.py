from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from common_schemas.exceptions import AuthorizationError, NotFoundError, ValidationError

from ...domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from ...domain.ports.skill_repository import SkillRepository
from ...domain.value_objects.skill_state import SkillState


class UpdatePersonalSkillUseCase:
    """개인 스킬 메타 수정 — personal skills 편집 UI (REQ-013, 가원 요청).

    api_server `PUT /skills/personal/{id}` 라우트가 조립. 수정 가능 필드는 `name`/`description`/`tags`
    (2026-05-26 박아름 결정 — 노드 스펙/임베딩/문서 재생성은 후속). 신뢰 경계:

    - 인가: **owner만**(`actor_user_id == owner_user_id`) — 아니면 `AuthorizationError`(fail-closed).
      `SkillApprovalPolicy`의 personal 규칙(actor==owner)과 일관.
    - lifecycle: **DRAFT 상태만** 수정 — review/approved/published는 보호(전이 후엔 게시 흐름이 관리).
      `SkillLifecycle`(전이 규칙)과 별개의 "편집 가능 조건"이라 use case에서 명시 검증.
    - 빈 문자열 name/description은 거부(`ValidationError`) — `model_copy`는 재검증하지 않으므로 직접 가드.

    부분 수정: None인 필드는 변경하지 않는다. 변경 항목이 없으면 저장 없이 현재 스킬 반환.
    """

    _EDITABLE_STATE = SkillState.DRAFT

    def __init__(self, repo: SkillRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        skill_id: UUID,
        actor_user_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> MarketplacePersonalSkill:
        skill = await self._repo.get_personal(skill_id)
        if skill is None:
            raise NotFoundError(f"Personal skill {skill_id} not found")

        if skill.owner_user_id != actor_user_id:
            raise AuthorizationError(
                f"User {actor_user_id} is not the owner of personal skill {skill_id}"
            )

        if SkillState(skill.lifecycle_state) != self._EDITABLE_STATE:
            raise ValidationError(
                f"Personal skill {skill_id} is '{skill.lifecycle_state}' — only DRAFT skills are editable"
            )

        changes: dict[str, object] = {}
        if name is not None:
            if not name.strip():
                raise ValidationError("name must not be empty")
            changes["name"] = name
        if description is not None:
            if not description.strip():
                raise ValidationError("description must not be empty")
            changes["description"] = description
        if tags is not None:
            changes["tags"] = tags

        if not changes:
            return skill

        changes["updated_at"] = datetime.now(UTC)
        updated = skill.model_copy(update=changes)
        return await self._repo.save_personal(updated)
