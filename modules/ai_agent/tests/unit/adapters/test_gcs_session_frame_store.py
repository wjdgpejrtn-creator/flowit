"""GCSSessionFrameStore 단위 테스트 — GCS 호출은 전부 mock."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ai_agent.adapters.memory.gcs_session_frame_store import GCSSessionFrameStore
from ai_agent.domain.entities.session_ref import SessionRef
from common_schemas.transport import PipelineStatusFrame, SessionFrame


def _make_ref(session_id=None, user_id=None, workflow_id=None) -> SessionRef:
    return SessionRef(
        session_id=session_id or uuid4(),
        user_id=user_id or uuid4(),
        workflow_id=workflow_id,
        created_at=datetime.now(timezone.utc),
        message_preview="테스트 메시지",
    )


def _make_frames() -> list:
    return [
        SessionFrame(session_id=uuid4(), langgraph_thread_id=uuid4()),
        PipelineStatusFrame(service_name="security", status="completed", elapsed_ms=10),
    ]


def _mock_store(bucket_name: str = "test-bucket") -> GCSSessionFrameStore:
    store = GCSSessionFrameStore(bucket_name=bucket_name)
    mock_bucket = MagicMock()
    store._bucket = mock_bucket
    return store


class TestSaveSession:
    @pytest.mark.asyncio
    async def test_save_session_uploads_frames_json(self):
        """save_session이 프레임을 JSON으로 직렬화해서 GCS에 업로드한다."""
        store = _mock_store()
        ref = _make_ref()
        frames = _make_frames()

        blob = MagicMock()
        store._bucket.blob.return_value = blob

        # 호출 순서: frames upload → index download(없으면 예외) → index upload
        call_results = [None, Exception("not found"), None]
        call_idx = 0

        async def side_effect(fn, *args, **kwargs):
            nonlocal call_idx
            result = call_results[call_idx]
            call_idx += 1
            if isinstance(result, Exception):
                raise result
            return result

        with patch("asyncio.to_thread", side_effect=side_effect):
            await store.save_session(ref, frames)

        assert call_idx == 3  # upload frames + load index + upload index

    @pytest.mark.asyncio
    async def test_save_session_updates_index(self):
        """save_session이 프레임 저장 후 인덱스도 업데이트한다."""
        store = _mock_store()
        ref = _make_ref()
        frames = _make_frames()

        blob = MagicMock()
        store._bucket.blob.return_value = blob

        call_idx = 0
        async def side_effect(fn, *args, **kwargs):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 2:  # index load — 없는 경우
                raise Exception("not found")
            return None

        with patch("asyncio.to_thread", side_effect=side_effect):
            await store.save_session(ref, frames)

        assert call_idx == 3  # frames 업로드 + index 로드 + index 저장

    @pytest.mark.asyncio
    async def test_save_session_deduplicates_index(self):
        """동일 session_id가 인덱스에 있으면 중복 추가하지 않는다."""
        store = _mock_store()
        user_id = uuid4()
        session_id = uuid4()
        ref = _make_ref(session_id=session_id, user_id=user_id)
        frames = _make_frames()

        existing_ref = _make_ref(session_id=session_id, user_id=user_id)
        existing_index = [existing_ref.model_dump(mode="json")]

        blob = MagicMock()
        store._bucket.blob.return_value = blob

        upload_payloads = []
        async def mock_to_thread(fn, *args, **kwargs):
            if fn == blob.download_as_bytes:
                return json.dumps(existing_index).encode()
            if fn == blob.upload_from_string:
                upload_payloads.append(args[0])
            return None

        with patch("asyncio.to_thread", side_effect=mock_to_thread):
            await store.save_session(ref, frames)

        # 인덱스 업로드 페이로드 확인 — session_id 중복 없어야 함
        index_payload = json.loads(upload_payloads[-1])
        session_ids = [item["session_id"] for item in index_payload]
        assert session_ids.count(str(session_id)) == 1


class TestLoadFrames:
    @pytest.mark.asyncio
    async def test_load_frames_returns_parsed_frames(self):
        """GCS에서 읽은 JSON을 AnySSEFrame 리스트로 파싱해서 반환한다."""
        store = _mock_store()
        session_id = uuid4()
        user_id = uuid4()
        frames = _make_frames()
        raw = json.dumps([f.model_dump(mode="json") for f in frames]).encode()

        blob = MagicMock()
        store._bucket.blob.return_value = blob

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = raw
            result = await store.load_frames(session_id, user_id)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_load_frames_returns_empty_on_missing(self):
        """GCS에 파일 없으면 빈 리스트 반환 (예외 삼킴)."""
        store = _mock_store()

        blob = MagicMock()
        store._bucket.blob.return_value = blob

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = Exception("blob not found")
            result = await store.load_frames(uuid4(), uuid4())

        assert result == []

    @pytest.mark.asyncio
    async def test_load_frames_skips_invalid_items(self):
        """파싱 불가 항목은 건너뛰고 나머지만 반환한다."""
        store = _mock_store()
        valid_frame = _make_frames()[1]
        raw = json.dumps([
            valid_frame.model_dump(mode="json"),
            {"type": "unknown_garbage", "data": {}},
        ]).encode()

        blob = MagicMock()
        store._bucket.blob.return_value = blob

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = raw
            result = await store.load_frames(uuid4(), uuid4())

        assert len(result) == 1


class TestListSessions:
    @pytest.mark.asyncio
    async def test_list_sessions_returns_limited(self):
        """list_sessions가 limit 개수만큼 반환한다."""
        store = _mock_store()
        user_id = uuid4()
        refs = [_make_ref(user_id=user_id) for _ in range(5)]
        raw = json.dumps([r.model_dump(mode="json") for r in refs]).encode()

        blob = MagicMock()
        store._bucket.blob.return_value = blob

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = raw
            result = await store.list_sessions(user_id, limit=3)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_sessions_returns_empty_on_missing_index(self):
        """인덱스 파일 없으면 빈 리스트 반환."""
        store = _mock_store()

        blob = MagicMock()
        store._bucket.blob.return_value = blob

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = Exception("not found")
            result = await store.list_sessions(uuid4())

        assert result == []
