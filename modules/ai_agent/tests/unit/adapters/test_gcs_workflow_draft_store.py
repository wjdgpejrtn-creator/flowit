"""GCSWorkflowDraftStore 단위 테스트."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ai_agent.adapters.memory.gcs_workflow_draft_store import GCSWorkflowDraftStore


def _make_store() -> GCSWorkflowDraftStore:
    return GCSWorkflowDraftStore(bucket_name="test-bucket")


def _make_workflow():
    from common_schemas.workflow import WorkflowSchema
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="테스트 워크플로우",
        nodes=[],
        connections=[],
        owner_user_id=uuid4(),
        scope="private",
        is_draft=False,
    )


def _make_mock_bucket(blob_data: bytes | None = None, raise_on_download: bool = False):
    mock_blob = MagicMock()
    if raise_on_download:
        mock_blob.download_as_bytes.side_effect = Exception("Not Found")
    else:
        mock_blob.download_as_bytes.return_value = blob_data or b""
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    return mock_bucket, mock_blob


class TestSaveDraft:
    @pytest.mark.asyncio
    async def test_uploads_to_correct_path(self):
        """save_draft가 drafts/{session_id}.json 경로에 업로드한다."""
        store = _make_store()
        session_id = uuid4()
        workflow = _make_workflow()
        mock_bucket, mock_blob = _make_mock_bucket()

        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            await store.save_draft(session_id, workflow)

        mock_bucket.blob.assert_called_once_with(f"drafts/{session_id}.json")
        mock_blob.upload_from_string.assert_called_once()
        assert mock_blob.upload_from_string.call_args[0][1] == "application/json; charset=utf-8"

    @pytest.mark.asyncio
    async def test_uploaded_content_is_deserializable(self):
        """업로드된 내용이 WorkflowSchema로 역직렬화 가능하다."""
        from common_schemas.workflow import WorkflowSchema

        store = _make_store()
        session_id = uuid4()
        workflow = _make_workflow()
        mock_bucket, mock_blob = _make_mock_bucket()

        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            await store.save_draft(session_id, workflow)

        payload = mock_blob.upload_from_string.call_args[0][0]
        restored = WorkflowSchema.model_validate_json(payload)
        assert restored.workflow_id == workflow.workflow_id


class TestLoadDraft:
    @pytest.mark.asyncio
    async def test_returns_workflow_on_success(self):
        """저장된 draft를 정상적으로 로드한다."""
        store = _make_store()
        session_id = uuid4()
        workflow = _make_workflow()
        raw = workflow.model_dump_json().encode("utf-8")
        mock_bucket, _ = _make_mock_bucket(blob_data=raw)

        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            result = await store.load_draft(session_id)

        assert result is not None
        assert result.workflow_id == workflow.workflow_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """GCS에 파일 없으면 None 반환 — 크래시 없음."""
        store = _make_store()
        mock_bucket, _ = _make_mock_bucket(raise_on_download=True)

        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            result = await store.load_draft(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_corrupt_json(self):
        """손상된 JSON이면 None 반환."""
        store = _make_store()
        mock_bucket, _ = _make_mock_bucket(blob_data=b"not-json")

        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            result = await store.load_draft(uuid4())

        assert result is None


class TestDeleteDraft:
    @pytest.mark.asyncio
    async def test_deletes_correct_blob(self):
        """delete_draft가 올바른 경로의 blob을 삭제한다."""
        store = _make_store()
        session_id = uuid4()
        mock_bucket, mock_blob = _make_mock_bucket()

        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            await store.delete_draft(session_id)

        mock_bucket.blob.assert_called_once_with(f"drafts/{session_id}.json")
        mock_blob.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_raise_when_blob_missing(self):
        """blob이 없어도 예외 없이 통과한다."""
        store = _make_store()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.delete.side_effect = Exception("Not Found")
        mock_bucket.blob.return_value = mock_blob

        with patch.object(store, "_get_bucket", return_value=mock_bucket):
            await store.delete_draft(uuid4())


class TestDraftKey:
    def test_draft_key_format(self):
        """_draft_key가 올바른 경로 형식을 반환한다."""
        store = _make_store()
        session_id = uuid4()
        assert store._draft_key(session_id) == f"drafts/{session_id}.json"
