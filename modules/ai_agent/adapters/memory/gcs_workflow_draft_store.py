"""GCSWorkflowDraftStore — WorkflowDraftStore의 GCS 구현체."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import UUID

from common_schemas.workflow import WorkflowSchema

from ...domain.ports.workflow_draft_store import WorkflowDraftStore

if TYPE_CHECKING:
    from google.cloud.storage import Bucket


class GCSWorkflowDraftStore(WorkflowDraftStore):
    """WorkflowDraftStore의 GCS 구현체.

    Modal 다중 컨테이너 환경에서도 draft를 일관되게 저장/조회한다.
    저장 경로: gs://{bucket}/drafts/{session_id}.json
    버킷: GCS_SESSION_BUCKET 환경변수 (GCSSessionFrameStore와 동일 버킷).
    """

    _DRAFT_PREFIX = "drafts"

    def __init__(self, bucket_name: str | None = None) -> None:
        self._bucket_name = bucket_name or os.getenv("GCS_SESSION_BUCKET", "")
        self._bucket: Bucket | None = None

    def _get_bucket(self) -> Bucket:
        if self._bucket is None:
            from google.cloud import storage
            self._bucket = storage.Client().bucket(self._bucket_name)
        return self._bucket

    def _draft_key(self, session_id: UUID) -> str:
        return f"{self._DRAFT_PREFIX}/{session_id}.json"

    async def save_draft(self, session_id: UUID, draft: WorkflowSchema) -> None:
        import asyncio
        payload = draft.model_dump_json().encode("utf-8")
        bucket = self._get_bucket()
        blob = bucket.blob(self._draft_key(session_id))
        await asyncio.to_thread(blob.upload_from_string, payload, "application/json; charset=utf-8")

    async def load_draft(self, session_id: UUID) -> WorkflowSchema | None:
        import asyncio
        bucket = self._get_bucket()
        blob = bucket.blob(self._draft_key(session_id))
        try:
            raw: bytes = await asyncio.to_thread(blob.download_as_bytes)
            return WorkflowSchema.model_validate_json(raw)
        except Exception:
            return None

    async def delete_draft(self, session_id: UUID) -> None:
        import asyncio
        bucket = self._get_bucket()
        blob = bucket.blob(self._draft_key(session_id))
        try:
            await asyncio.to_thread(blob.delete)
        except Exception:
            pass
