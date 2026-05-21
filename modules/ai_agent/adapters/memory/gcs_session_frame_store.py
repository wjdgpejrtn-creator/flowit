from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import TypeAdapter

from common_schemas.transport import AnySSEFrame

from ...domain.entities.session_ref import SessionRef
from ...domain.ports.session_frame_store import SessionFrameStore

if TYPE_CHECKING:
    from google.cloud.storage import Bucket

_FRAME_ADAPTER: TypeAdapter[AnySSEFrame] = TypeAdapter(AnySSEFrame)
_INDEX_MAX = 100  # 인덱스에 보관할 세션 최대 수


class GCSSessionFrameStore(SessionFrameStore):
    """SessionFrameStore의 GCS 구현체.

    버킷: GCS_SESSION_BUCKET 환경변수.
    GCSMemoryStore와 동일한 동기 GCS 클라이언트 패턴.
    """

    def __init__(self, bucket_name: str | None = None) -> None:
        self._bucket_name = bucket_name or os.getenv("GCS_SESSION_BUCKET", "")
        self._bucket: Bucket | None = None

    def _get_bucket(self) -> Bucket:
        if self._bucket is None:
            from google.cloud import storage  # lazy import — 로컬 단위 테스트 시 mock 가능

            self._bucket = storage.Client().bucket(self._bucket_name)
        return self._bucket

    def _frames_key(self, user_id: UUID, session_id: UUID) -> str:
        return f"sessions/{user_id}/{session_id}.json"

    def _index_key(self, user_id: UUID) -> str:
        return f"sessions/{user_id}/index.json"

    # ── public ──────────────────────────────────────────────────────────────

    async def save_session(self, ref: SessionRef, frames: list[AnySSEFrame]) -> None:
        import asyncio

        payload = json.dumps([f.model_dump(mode="json") for f in frames], ensure_ascii=False)
        bucket = self._get_bucket()
        frames_blob = bucket.blob(self._frames_key(ref.user_id, ref.session_id))
        await asyncio.to_thread(
            frames_blob.upload_from_string, payload, "application/json; charset=utf-8"
        )

        index = await self._load_index(ref.user_id)
        index = [r for r in index if r.session_id != ref.session_id]
        index.insert(0, ref)
        await self._save_index(ref.user_id, index[:_INDEX_MAX])

    async def load_frames(self, session_id: UUID, user_id: UUID) -> list[AnySSEFrame]:
        import asyncio

        bucket = self._get_bucket()
        blob = bucket.blob(self._frames_key(user_id, session_id))
        try:
            raw: bytes = await asyncio.to_thread(blob.download_as_bytes)
        except Exception:
            return []
        frames: list[AnySSEFrame] = []
        for item in json.loads(raw):
            try:
                frames.append(_FRAME_ADAPTER.validate_python(item))
            except Exception:
                pass
        return frames

    async def list_sessions(self, user_id: UUID, limit: int = 20) -> list[SessionRef]:
        return (await self._load_index(user_id))[:limit]

    # ── private ─────────────────────────────────────────────────────────────

    async def _load_index(self, user_id: UUID) -> list[SessionRef]:
        import asyncio

        bucket = self._get_bucket()
        blob = bucket.blob(self._index_key(user_id))
        try:
            raw: bytes = await asyncio.to_thread(blob.download_as_bytes)
        except Exception:
            return []
        refs: list[SessionRef] = []
        for item in json.loads(raw):
            try:
                refs.append(SessionRef.model_validate(item))
            except Exception:
                pass
        return refs

    async def _save_index(self, user_id: UUID, refs: list[SessionRef]) -> None:
        import asyncio

        payload = json.dumps([r.model_dump(mode="json") for r in refs], ensure_ascii=False)
        bucket = self._get_bucket()
        blob = bucket.blob(self._index_key(user_id))
        await asyncio.to_thread(blob.upload_from_string, payload, "application/json; charset=utf-8")
