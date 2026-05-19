from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING
from uuid import UUID

from ...domain.entities.memory_file import MemoryFile, MemoryFileRef
from ...domain.ports.personal_memory_store import PersonalMemoryStore

if TYPE_CHECKING:
    from google.cloud.storage import Bucket

_INDEX_FILENAME = "MEMORY.md"
_INDEX_LINE_RE = re.compile(r"^- \[([^\]]+)\]\(([^)]+)\) — (.+)$")


def _parse_index(content: str) -> list[MemoryFileRef]:
    refs: list[MemoryFileRef] = []
    for line in content.splitlines():
        m = _INDEX_LINE_RE.match(line.strip())
        if m:
            refs.append(
                MemoryFileRef(name=m.group(1), filename=m.group(2), description=m.group(3))
            )
    return refs


def _serialize_index(refs: list[MemoryFileRef]) -> str:
    lines = ["# Memory Index", ""]
    for ref in refs:
        lines.append(f"- [{ref.name}]({ref.filename}) — {ref.description}")
    return "\n".join(lines) + "\n"


def _parse_md_file(filename: str, raw: str) -> MemoryFile:
    if raw.startswith("---"):
        try:
            end = raw.index("---", 3)
        except ValueError:
            return MemoryFile(
                filename=filename,
                name=filename.removesuffix(".md"),
                description="",
                memory_type="project",
                body=raw,
            )
        fm_str = raw[3:end]
        body = raw[end + 3:].strip()
        fm = _parse_frontmatter(fm_str)
        metadata = fm.get("metadata", {}) if isinstance(fm.get("metadata"), dict) else {}
        mem_type = metadata.get("type", "project")
        return MemoryFile(
            filename=filename,
            name=fm.get("name", filename.removesuffix(".md")),
            description=fm.get("description", ""),
            memory_type=mem_type,  # type: ignore[arg-type]
            body=body,
        )
    return MemoryFile(
        filename=filename,
        name=filename.removesuffix(".md"),
        description="",
        memory_type="project",
        body=raw,
    )


def _serialize_md_file(file: MemoryFile) -> str:
    return (
        f"---\n"
        f"name: {file.name}\n"
        f"description: {file.description}\n"
        f"metadata:\n"
        f"  type: {file.memory_type}\n"
        f"---\n\n"
        f"{file.body}\n"
    )


def _parse_frontmatter(fm_str: str) -> dict[str, str | dict[str, str]]:
    result: dict[str, str | dict[str, str]] = {}
    pending_key: str | None = None
    nested: dict[str, str] = {}
    for line in fm_str.splitlines():
        stripped = line.rstrip()
        if not stripped:
            continue
        if stripped.startswith("  ") and ":" in stripped:
            k, _, v = stripped.strip().partition(":")
            nested[k.strip()] = v.strip()
        elif ":" in stripped:
            if pending_key is not None and nested:
                result[pending_key] = nested
                nested = {}
            k, _, v = stripped.partition(":")
            key = k.strip()
            val = v.strip()
            if val:
                result[key] = val
                pending_key = None
            else:
                pending_key = key
                nested = {}
    if pending_key is not None and nested:
        result[pending_key] = nested
    return result


class GCSMemoryStore(PersonalMemoryStore):
    """PersonalMemoryStore의 GCS 구현체.

    버킷: GCS_PERSONAL_BUCKET 환경변수 (Modal Secret: agent-personalization-secret).
    캐시: 세션 중 중복 GCS 다운로드 방지 (cleanup()으로 해제).
    """

    def __init__(self, bucket_name: str | None = None) -> None:
        self._bucket_name = bucket_name or os.getenv("GCS_PERSONAL_BUCKET", "")
        self._bucket: Bucket | None = None
        self._cache: dict[UUID, dict[str, bytes]] = {}

    def _get_bucket(self) -> Bucket:
        if self._bucket is None:
            from google.cloud import storage  # lazy import — 로컬 단위 테스트 시 mock 가능

            self._bucket = storage.Client().bucket(self._bucket_name)
        return self._bucket

    def _blob_key(self, user_id: UUID, filename: str) -> str:
        return f"users/{user_id}/{filename}"

    async def _download(self, user_id: UUID, filename: str) -> bytes | None:
        user_cache = self._cache.setdefault(user_id, {})
        if filename in user_cache:
            return user_cache[filename]
        try:
            bucket = self._get_bucket()
            blob = bucket.blob(self._blob_key(user_id, filename))
            data = blob.download_as_bytes()
            user_cache[filename] = data
            return data
        except Exception:
            return None

    async def _upload(self, user_id: UUID, filename: str, data: bytes) -> None:
        bucket = self._get_bucket()
        key = self._blob_key(user_id, filename)
        blob = bucket.blob(key)
        try:
            blob.reload()
            generation = blob.generation
        except Exception:
            generation = 0
        try:
            from google.api_core.exceptions import PreconditionFailed

            blob.upload_from_string(
                data,
                content_type="text/plain; charset=utf-8",
                if_generation_match=generation,
            )
        except PreconditionFailed:
            # 동시 write 충돌 — 재시도 없이 전파 (호출자가 판단)
            raise
        self._cache.setdefault(user_id, {})[filename] = data

    # ── index ──────────────────────────────────────────────────────────────

    async def load_index(self, user_id: UUID) -> list[MemoryFileRef]:
        raw = await self._download(user_id, _INDEX_FILENAME)
        if raw is None:
            return []
        return _parse_index(raw.decode("utf-8"))

    async def save_index(self, user_id: UUID, refs: list[MemoryFileRef]) -> None:
        content = _serialize_index(refs)
        await self._upload(user_id, _INDEX_FILENAME, content.encode("utf-8"))

    # ── individual files ────────────────────────────────────────────────────

    async def load_file(self, user_id: UUID, filename: str) -> MemoryFile:
        raw = await self._download(user_id, filename)
        if raw is None:
            raise FileNotFoundError(f"Memory file not found: users/{user_id}/{filename}")
        return _parse_md_file(filename, raw.decode("utf-8"))

    async def save_file(self, user_id: UUID, file: MemoryFile) -> None:
        content = _serialize_md_file(file)
        await self._upload(user_id, file.filename, content.encode("utf-8"))

    async def delete_file(self, user_id: UUID, filename: str) -> None:
        try:
            bucket = self._get_bucket()
            blob = bucket.blob(self._blob_key(user_id, filename))
            blob.delete()
        except Exception:
            pass
        self._cache.get(user_id, {}).pop(filename, None)

    # ── embeddings ──────────────────────────────────────────────────────────

    async def load_embedding(self, user_id: UUID, name: str) -> list[float] | None:
        emb_filename = f"{name}.emb.json"
        raw = await self._download(user_id, emb_filename)
        if raw is None:
            return None
        return json.loads(raw)["embedding"]

    async def save_embedding(self, user_id: UUID, name: str, embedding: list[float]) -> None:
        emb_filename = f"{name}.emb.json"
        data = json.dumps({"embedding": embedding}, ensure_ascii=False).encode("utf-8")
        await self._upload(user_id, emb_filename, data)

    # ── lifecycle ───────────────────────────────────────────────────────────

    async def cleanup(self, user_id: UUID) -> None:
        self._cache.pop(user_id, None)
