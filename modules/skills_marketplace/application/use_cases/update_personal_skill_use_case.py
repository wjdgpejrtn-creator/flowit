from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from common_schemas import SkillDocument
from common_schemas.exceptions import AuthorizationError, NotFoundError, ValidationError

from ...domain.entities.marketplace_personal_skill import MarketplacePersonalSkill
from ...domain.ports.skill_document_store import SkillDocumentStore
from ...domain.ports.skill_repository import SkillRepository


class UpdatePersonalSkillUseCase:
    """개인 스킬 수정 — personal skills 편집 UI (REQ-013).

    api_server `PUT /skills/personal/{id}` 라우트가 조립. 수정 가능 필드는 `name`/`description`/
    `tags`(메타) + `instructions`(지침서 SKILL.md 본문). 신뢰 경계:

    - 인가: **owner만**(`actor_user_id == owner_user_id`) — 아니면 `AuthorizationError`(fail-closed).
      `SkillApprovalPolicy`의 personal 규칙(actor==owner)과 일관.
    - lifecycle: **상태 제약 없음** — owner는 게시(PUBLISHED) 스킬도 수정할 수 있다(2026-06-02
      황대원 결정, 상세 페이지 편집 UX). 기존엔 DRAFT만 허용했으나(2026-05-26 박아름) 게시 후
      본문/메타 정정 요구로 완화. ⚠️ **임베딩 staleness 후속**: description/instructions를 수정해도
      검색 임베딩(768d)은 재계산하지 않는다 — 게시 스킬을 수정하면 Composer 검색 벡터가 옛 본문
      기준으로 남는다. 임베딩 재생성(`PublishSkillUseCase`의 embedder 경로 재사용)은 별도 후속
      (박아름 — "노드 스펙/임베딩/문서 재생성은 후속" 미해소분).
    - 빈 문자열 name/description은 거부(`ValidationError`) — `model_copy`는 재검증하지 않으므로 직접 가드.

    부분 수정: None인 필드는 변경하지 않는다. 변경 항목이 없으면 저장 없이 현재 스킬 반환.
    `tags`는 None(미변경)과 `[]`(빈 리스트)를 구분 — `tags=[]`는 **태그 전체 비움**으로 처리한다.

    ADR-0017 이중 저장: `instructions`가 주어지고 `doc_store`가 주입돼 있으면 SkillDocument(markdown)를
    GCS에 재저장하고 반환된 gs:// URI를 메타데이터(`skill_document_uri`)에 반영한다. `doc_store` 미주입
    (단위 테스트 등)이면 본문 저장은 건너뛴다 — 메타만 갱신(`CreateDraftSkillUseCase`와 일관).
    """

    def __init__(self, repo: SkillRepository, doc_store: SkillDocumentStore | None = None) -> None:
        self._repo = repo
        self._doc_store = doc_store

    async def execute(
        self,
        skill_id: UUID,
        actor_user_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        instructions: str | None = None,
    ) -> MarketplacePersonalSkill:
        skill = await self._repo.get_personal(skill_id)
        if skill is None:
            raise NotFoundError(f"Personal skill {skill_id} not found")

        if skill.owner_user_id != actor_user_id:
            raise AuthorizationError(
                f"User {actor_user_id} is not the owner of personal skill {skill_id}"
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

        # 지침서 본문(SKILL.md) 재저장 — instructions가 오고 doc_store가 있을 때만(ADR-0017).
        # 문서의 name/description은 이번 수정으로 확정될 최종값을 쓴다(메타와 본문 헤더 일관).
        write_doc = instructions is not None and self._doc_store is not None
        if write_doc:
            document = SkillDocument(
                skill_id=skill_id,
                name=str(changes.get("name", skill.name)),
                description=str(changes.get("description", skill.description)),
                instructions=instructions,  # type: ignore[arg-type]  # write_doc가 not-None 보장
            )
            uri = await self._doc_store.save(skill_id, document)  # type: ignore[union-attr]
            if uri != skill.skill_document_uri:
                changes["skill_document_uri"] = uri

        if not changes:
            return skill

        changes["updated_at"] = datetime.now(UTC)
        updated = skill.model_copy(update=changes)
        return await self._repo.save_personal(updated)
