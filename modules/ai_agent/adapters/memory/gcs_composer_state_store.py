"""GCSComposerStateStore — ComposerStateStore의 GCS 구현체 (REQ-013 two-shot HITL)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ...domain.ports.composer_state_store import ComposerStateStore

if TYPE_CHECKING:
    from google.cloud.storage import Bucket

_logger = logging.getLogger(__name__)


class GCSComposerStateStore(ComposerStateStore):
    """ComposerStateStore의 GCS 구현체.

    Modal 다중 컨테이너(stateless)에서도 two-shot 1차 상태를 일관 저장/조회한다.
    저장 경로: gs://{bucket}/composer_state/{session_id}.json
    버킷: GCS_SESSION_BUCKET 환경변수 (GCSSessionFrameStore/GCSWorkflowDraftStore와 동일).
    """

    _STATE_PREFIX = "composer_state"

    def __init__(self, bucket_name: str | None = None) -> None:
        self._bucket_name = bucket_name or os.getenv("GCS_SESSION_BUCKET", "")
        self._bucket: Bucket | None = None

    def _get_bucket(self) -> Bucket:
        if self._bucket is None:
            from google.cloud import storage
            self._bucket = storage.Client().bucket(self._bucket_name)
        return self._bucket

    def _state_key(self, session_id: UUID) -> str:
        return f"{self._STATE_PREFIX}/{session_id}.json"

    async def save_state(self, session_id: UUID, state: dict[str, Any]) -> None:
        # default=str: UUID 등 비-JSON 타입 안전 직렬화. composer가 Pydantic 필드는
        # model_dump로 미리 직렬화해 넘긴다(복원 측이 model_validate로 재구성).
        payload = json.dumps(state, ensure_ascii=False, default=str).encode("utf-8")
        bucket = self._get_bucket()
        blob = bucket.blob(self._state_key(session_id))
        await asyncio.to_thread(blob.upload_from_string, payload, "application/json; charset=utf-8")

    async def load_state(self, session_id: UUID) -> dict[str, Any] | None:
        """저장된 재개 상태 조회.

        미존재(NotFound)·손상 JSON → None(진짜 만료/오타). 일시적 GCS·인증 오류는
        **예외를 전파**해 호출부(resume)가 만료와 구분(재시도 안내)하도록 한다.
        """
        bucket = self._get_bucket()
        blob = bucket.blob(self._state_key(session_id))
        try:
            raw: bytes = await asyncio.to_thread(blob.download_as_bytes)
        except Exception as exc:
            # NotFound(404) → 미존재(None). 그 외(인증/네트워크/5xx)는 일시적 오류로 전파해
            # 호출부(resume)가 만료와 구분(재시도 안내)하게 한다. import 의존 없이 분류.
            if getattr(exc, "code", None) == 404 or type(exc).__name__ == "NotFound":
                return None
            _logger.warning("composer_state load 일시 오류 (session=%s) — 전파", session_id)
            raise
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            _logger.warning("composer_state 손상 JSON (session=%s) → None", session_id)
            return None

    async def delete_state(self, session_id: UUID) -> None:
        bucket = self._get_bucket()
        blob = bucket.blob(self._state_key(session_id))
        try:
            await asyncio.to_thread(blob.delete)
        except Exception as exc:  # 정리 단계 — 멱등, 실패해도 비치명적(다음 1차가 덮어씀)
            _logger.debug("composer_state delete no-op (session=%s): %s", session_id, exc)
