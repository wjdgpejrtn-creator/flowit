"""GCS-backed PersonalMemoryStore.

Storage layout:
    gs://{GCS_PERSONAL_BUCKET}/users/{user_id}/
        MEMORY.md        — index (markdown list of entries)
        {name}.md        — individual skill file with YAML frontmatter

Each skill file frontmatter:
    ---
    name: <str>
    description: <str>
    type: user | feedback | project | reference
    updated_at: <ISO-8601>
    embedding: [float, ...]  # optional, BGE-M3 768d
    ---
    <body>

Environment:
    GCS_PERSONAL_BUCKET  — bucket name (required)
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from ai_agent.domain.entities.personal_skill import PersonalSkill
from ai_agent.domain.ports.personal_memory_store import PersonalMemoryStore

if TYPE_CHECKING:
    from google.cloud.storage import Bucket

_INDEX_FILENAME = "MEMORY.md"


class GCSMemoryStore(PersonalMemoryStore):
    def __init__(self, bucket_name: str | None = None) -> None:
        self._bucket_name = bucket_name or os.getenv("GCS_PERSONAL_BUCKET", "")
        self._bucket: Bucket | None = None
        self._cache: dict[UUID, list[PersonalSkill]] = {}

    def _get_bucket(self) -> Bucket:
        if self._bucket is None:
            from google.cloud import storage

            client = storage.Client()
            self._bucket = client.bucket(self._bucket_name)
        return self._bucket

    def _index_key(self, user_id: UUID) -> str:
        return f"users/{user_id}/{_INDEX_FILENAME}"

    def _skill_key(self, user_id: UUID, name: str) -> str:
        return f"users/{user_id}/{name}.md"

    async def load_index(self, user_id: UUID) -> str:
        bucket = self._get_bucket()
        blob = bucket.blob(self._index_key(user_id))
        exists = await asyncio.to_thread(blob.exists)
        if not exists:
            return ""
        return await asyncio.to_thread(blob.download_as_text, encoding="utf-8")

    async def save_index(self, user_id: UUID, content: str) -> None:
        bucket = self._get_bucket()
        blob = bucket.blob(self._index_key(user_id))
        await asyncio.to_thread(
            blob.upload_from_string, content.encode("utf-8"), content_type="text/markdown"
        )

    async def load_entry(self, user_id: UUID, name: str) -> PersonalSkill:
        import frontmatter

        bucket = self._get_bucket()
        blob = bucket.blob(self._skill_key(user_id, name))
        text = await asyncio.to_thread(blob.download_as_text, encoding="utf-8")
        post = frontmatter.loads(text)
        return PersonalSkill(
            user_id=user_id,
            skill_type=post.metadata["type"],
            name=post.metadata["name"],
            description=post.metadata.get("description", ""),
            body=post.content,
            embedding=post.metadata.get("embedding"),
            updated_at=_parse_updated_at(post.metadata.get("updated_at")),
        )

    async def save_entry(self, user_id: UUID, skill: PersonalSkill) -> None:
        import frontmatter

        metadata: dict = {
            "name": skill.name,
            "description": skill.description,
            "type": skill.skill_type,
            "updated_at": skill.updated_at.isoformat(),
        }
        if skill.embedding is not None:
            metadata["embedding"] = skill.embedding

        post = frontmatter.Post(skill.body, **metadata)
        text = frontmatter.dumps(post)
        bucket = self._get_bucket()
        blob = bucket.blob(self._skill_key(user_id, skill.name))
        await asyncio.to_thread(
            blob.upload_from_string, text.encode("utf-8"), content_type="text/markdown"
        )

        if user_id in self._cache:
            updated = [s for s in self._cache[user_id] if s.name != skill.name]
            updated.append(skill)
            self._cache[user_id] = updated

    async def list_entries(self, user_id: UUID) -> list[PersonalSkill]:
        if user_id in self._cache:
            return self._cache[user_id]

        import frontmatter

        bucket = self._get_bucket()
        prefix = f"users/{user_id}/"

        blobs = await asyncio.to_thread(lambda: list(bucket.list_blobs(prefix=prefix)))

        entries: list[PersonalSkill] = []
        for blob in blobs:
            filename = blob.name.split("/")[-1]
            if filename == _INDEX_FILENAME or not filename.endswith(".md"):
                continue
            name = filename[:-3]
            text = await asyncio.to_thread(blob.download_as_text, encoding="utf-8")
            post = frontmatter.loads(text)
            entries.append(
                PersonalSkill(
                    user_id=user_id,
                    skill_type=post.metadata["type"],
                    name=post.metadata.get("name", name),
                    description=post.metadata.get("description", ""),
                    body=post.content,
                    embedding=post.metadata.get("embedding"),
                    updated_at=_parse_updated_at(post.metadata.get("updated_at")),
                )
            )
        self._cache[user_id] = entries
        return entries


def _parse_updated_at(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return datetime.now(timezone.utc)
