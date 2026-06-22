"""GCSComposerStateStore 단위 테스트 (REQ-013 two-shot HITL)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ai_agent.adapters.memory.gcs_composer_state_store import GCSComposerStateStore


def _make_store() -> GCSComposerStateStore:
    return GCSComposerStateStore(bucket_name="test-bucket")


def _make_mock_bucket(blob_data: bytes | None = None, raise_on_download: bool = False):
    mock_blob = MagicMock()
    if raise_on_download:
        mock_blob.download_as_bytes.side_effect = Exception("Not Found")
    else:
        mock_blob.download_as_bytes.return_value = blob_data or b""
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    return mock_bucket, mock_blob


class TestStateKey:
    def test_key_format(self):
        store = _make_store()
        sid = uuid4()
        assert store._state_key(sid) == f"composer_state/{sid}.json"


class TestSaveState:
    @pytest.mark.asyncio
    async def test_uploads_to_correct_path(self):
        store = _make_store()
        sid = uuid4()
        mock_bucket, mock_blob = _make_mock_bucket()
        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            await store.save_state(sid, {"intent": "draft", "node_candidates": []})
        mock_bucket.blob.assert_called_once_with(f"composer_state/{sid}.json")
        mock_blob.upload_from_string.assert_called_once()
        assert mock_blob.upload_from_string.call_args[0][1] == "application/json; charset=utf-8"

    @pytest.mark.asyncio
    async def test_uuid_in_blob_serialized_via_default_str(self):
        """비-JSON 타입(UUID)이 default=str로 안전 직렬화된다."""
        store = _make_store()
        mock_bucket, mock_blob = _make_mock_bucket()
        skill_id = uuid4()
        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            await store.save_state(uuid4(), {"selected_skill_id": skill_id})
        payload = mock_blob.upload_from_string.call_args[0][0]
        parsed = json.loads(payload)
        assert parsed["selected_skill_id"] == str(skill_id)


class TestLoadState:
    @pytest.mark.asyncio
    async def test_round_trip(self):
        store = _make_store()
        blob = {"intent": "draft", "node_candidates": [{"x": 1}], "intent_analyzed_entities": {"a": 1}}
        raw = json.dumps(blob).encode("utf-8")
        mock_bucket, _ = _make_mock_bucket(blob_data=raw)
        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            result = await store.load_state(uuid4())
        assert result == blob

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """미존재(404 NotFound) → None (진짜 만료/오타 session_id). google import 비의존 분류."""

        class _NotFoundError(Exception):  # google NotFound 모사 (code=404)
            code = 404

        store = _make_store()
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.side_effect = _NotFoundError("no such object")
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            result = await store.load_state(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_raises_on_transient_error(self):
        """일시적 GCS/인증 오류 → 예외 전파(호출부가 만료와 구분, LOW #3)."""
        store = _make_store()
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.side_effect = RuntimeError("503 backend error")
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            with pytest.raises(RuntimeError):
                await store.load_state(uuid4())

    @pytest.mark.asyncio
    async def test_returns_none_on_corrupt_json(self):
        store = _make_store()
        mock_bucket, _ = _make_mock_bucket(blob_data=b"not-json")
        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            result = await store.load_state(uuid4())
        assert result is None


class TestDeleteState:
    @pytest.mark.asyncio
    async def test_deletes_correct_blob(self):
        store = _make_store()
        sid = uuid4()
        mock_bucket, mock_blob = _make_mock_bucket()
        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            await store.delete_state(sid)
        mock_bucket.blob.assert_called_once_with(f"composer_state/{sid}.json")
        mock_blob.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotent_when_missing(self):
        store = _make_store()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.delete.side_effect = Exception("Not Found")
        mock_bucket.blob.return_value = mock_blob
        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            await store.delete_state(uuid4())  # 예외 없이 통과
