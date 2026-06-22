"""SkillDocumentStore (skills_marketplace Port) backed by ObjectStoragePort.

ADR-0017 이중 저장 중 "지침서" 측 어댑터. ObjectStoragePort 추상을 생성자 주입해
production은 GCSAdapter, 테스트는 LocalStorageAdapter/InMemoryObjectStorage로 swap.

SKILL.md 직렬화: YAML frontmatter(name/description) + markdown body(instructions).
description이 자유 텍스트(줄바꿈/콜론 가능)라 frontmatter는 YAML로 안전 직렬화/파싱
(`yaml.safe_load`/`yaml.safe_dump`).

GCS 키: `skills/{skill_id}/SKILL.md` (deterministic — 호출부가 skill_document_uri 구성).
스킬=지침서 묶음(#372)이므로 같은 디렉토리에 `COMPOSER.md`(composer측 지침)도 둔다.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import yaml
from common_schemas import SkillDocument
from common_schemas.exceptions import NotFoundError
from skills_marketplace.domain.ports.skill_document_store import SkillDocumentStore

from ..domain.ports.object_storage_port import ObjectStoragePort

_FENCE = "---\n"


def _key(skill_id: UUID) -> str:
    return f"skills/{skill_id}/SKILL.md"


def _composer_key(skill_id: UUID) -> str:
    return f"skills/{skill_id}/COMPOSER.md"


class GcsSkillDocumentStore(SkillDocumentStore):
    """SkillDocumentStore (skills_marketplace Port) backed by ObjectStoragePort.

    name이 "Gcs..."이지만 ObjectStoragePort 추상으로 어떤 구현이든 swap 가능 —
    production GCS 의도를 명시할 뿐 LocalStorageAdapter/InMemoryObjectStorage로
    테스트 가능. `load`는 NotFoundError(E-STORAGE-001) catch → None 반환에 의존하므로
    조합되는 ObjectStoragePort 구현이 키 부재 시 NotFoundError를 던져야 한다
    (GCSAdapter도 본 PR에서 정규화 완료).
    """

    def __init__(self, object_storage: ObjectStoragePort) -> None:
        self._storage = object_storage

    async def save(self, skill_id: UUID, document: SkillDocument) -> str:
        """SKILL.md(+COMPOSER.md)로 저장 후 SKILL.md의 `gs://{bucket}/{key}` URI 반환 —
        호출부가 그 값을 `skill_document_uri` 메타에 세팅. bucket 이름은 storage/infra
        영역이라 호출부(skills_marketplace use case)가 알면 config 누수.
        `ObjectStoragePort.upload`이 이미 URI를 반환하므로 그 값을 그대로 forward.

        COMPOSER.md(composer측 지침)는 `composer_instructions`가 비어 있지 않을 때만 쓴다
        (#372 detail 3 — 노드 지침만 있는 스킬은 COMPOSER.md 미생성). 반환 URI는 호출부
        계약(=SKILL.md) 유지를 위해 항상 SKILL.md.

        save는 upsert이므로, 빈 `composer_instructions`로 재저장(업데이트) 시 이전에 쓴
        COMPOSER.md를 **삭제**한다 — 안 그러면 stale COMPOSER.md가 잔존해 `load()`가 옛
        composer 지침을 반환(문서 ≠ 저장상태). 멱등 — 객체 부재면 NotFoundError swallow.
        """
        content = _serialize(document).encode("utf-8")
        uri = await self._storage.upload(_key(skill_id), content, metadata={})
        if document.composer_instructions:
            await self._storage.upload(
                _composer_key(skill_id), document.composer_instructions.encode("utf-8"), metadata={}
            )
        else:
            try:
                await self._storage.delete(_composer_key(skill_id))
            except NotFoundError:
                pass
        return uri

    async def load(self, skill_id: UUID) -> SkillDocument | None:
        try:
            raw = await self._storage.download(_key(skill_id))
        except NotFoundError:
            return None
        try:
            composer_raw = await self._storage.download(_composer_key(skill_id))
            composer_instructions = composer_raw.decode("utf-8")
        except NotFoundError:
            composer_instructions = ""
        return _deserialize(skill_id, raw.decode("utf-8"), composer_instructions)

    async def delete(self, skill_id: UUID) -> None:
        """멱등 — `ObjectStoragePort.delete`가 키 부재 시 NotFoundError를 던지면 swallow.
        DeletePersonalSkillUseCase가 DB row 삭제 직전 GCS 잔여물 정리에 사용 (orphan 방지).
        SKILL.md·COMPOSER.md 둘 다 정리(둘 다 부재여도 멱등).
        """
        for key in (_key(skill_id), _composer_key(skill_id)):
            try:
                await self._storage.delete(key)
            except NotFoundError:
                continue


def _serialize(document: SkillDocument) -> str:
    """SKILL.md 형식 — YAML frontmatter + markdown body."""
    frontmatter = yaml.safe_dump(
        {"name": document.name, "description": document.description},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip("\n")
    return f"{_FENCE}{frontmatter}\n{_FENCE}{document.instructions}"


def _deserialize(skill_id: UUID, raw: str, composer_instructions: str = "") -> SkillDocument:
    """SKILL.md(+COMPOSER.md body) → SkillDocument. frontmatter는 yaml.safe_load(인젝션 차단)."""
    if not raw.startswith(_FENCE):
        raise ValueError(f"Invalid SKILL.md (missing opening frontmatter fence): skill_id={skill_id}")
    after_open = raw[len(_FENCE):]
    close_marker = f"\n{_FENCE}"
    close_idx = after_open.find(close_marker)
    if close_idx == -1:
        raise ValueError(f"Invalid SKILL.md (unterminated frontmatter): skill_id={skill_id}")
    frontmatter_text = after_open[:close_idx]
    instructions = after_open[close_idx + len(close_marker):]
    meta: dict[str, Any] = yaml.safe_load(frontmatter_text) or {}
    return SkillDocument(
        skill_id=skill_id,
        name=meta.get("name", ""),
        description=meta.get("description", ""),
        instructions=instructions,
        composer_instructions=composer_instructions,
    )
