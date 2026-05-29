"""GCSMemoryStore unit tests — GCS 클라이언트를 mock하여 캐시·I/O 로직 검증."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from ai_agent.adapters.memory.gcs_memory_store import GCSMemoryStore, _parse_md_file, _serialize_md_file
from ai_agent.domain.entities.memory_file import MemoryFile, MemoryFileRef

USER_ID = UUID("00000000-0000-0000-0000-000000000001")

_SKILL_MD = (
    "---\n"
    "name: user-role\n"
    "description: 사용자 역할\n"
    "metadata:\n"
    "  type: user\n"
    "---\n\n"
    "Go 백엔드 전문가입니다\n"
)
_SKILL_MD_WITH_UPDATED_AT = (
    "---\n"
    "name: user-role\n"
    "description: 사용자 역할\n"
    "metadata:\n"
    "  type: user\n"
    "updated_at: 2026-05-21T10:00:00+00:00\n"
    "---\n\n"
    "Go 백엔드 전문가입니다\n"
)
_INDEX_MD = "# Memory Index\n\n- [user-role](user_role.md) — 사용자 역할\n"


def _store() -> tuple[GCSMemoryStore, MagicMock]:
    store = GCSMemoryStore(bucket_name="test-bucket")
    bucket = MagicMock()
    store._bucket = bucket
    return store, bucket


def _blob(data: bytes | None = None, *, generation: int = 42) -> MagicMock:
    b = MagicMock()
    b.generation = generation
    if data is None:
        b.download_as_bytes.side_effect = Exception("not found")
    else:
        b.download_as_bytes.return_value = data
    return b


class TestLoadIndex:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_missing(self):
        store, bucket = _store()
        bucket.blob.return_value = _blob(None)
        result = await store.load_index(USER_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_parsed_refs(self):
        store, bucket = _store()
        bucket.blob.return_value = _blob(_INDEX_MD.encode())
        result = await store.load_index(USER_ID)
        assert len(result) == 1
        assert result[0].name == "user-role"
        assert result[0].filename == "user_role.md"

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self):
        store, bucket = _store()
        bucket.blob.return_value = _blob(_INDEX_MD.encode())
        await store.load_index(USER_ID)
        await store.load_index(USER_ID)
        bucket.blob.assert_called_once()


class TestSaveIndex:
    @pytest.mark.asyncio
    async def test_uploads_serialized_refs(self):
        store, bucket = _store()
        blob = _blob()
        bucket.blob.return_value = blob
        refs = [MemoryFileRef(filename="role.md", name="role", description="역할")]
        await store.save_index(USER_ID, refs)
        blob.upload_from_string.assert_called_once()
        uploaded = blob.upload_from_string.call_args[0][0].decode()
        assert "role" in uploaded

    @pytest.mark.asyncio
    async def test_generation_zero_for_new_blob(self):
        store, bucket = _store()
        blob = MagicMock()
        blob.reload.side_effect = Exception("not found")
        bucket.blob.return_value = blob
        refs = [MemoryFileRef(filename="role.md", name="role", description="역할")]
        await store.save_index(USER_ID, refs)
        kwargs = blob.upload_from_string.call_args[1]
        assert kwargs["if_generation_match"] == 0


class TestLoadFile:
    @pytest.mark.asyncio
    async def test_parses_frontmatter(self):
        store, bucket = _store()
        bucket.blob.return_value = _blob(_SKILL_MD.encode())
        f = await store.load_file(USER_ID, "user_role.md")
        assert f.name == "user-role"
        assert f.memory_type == "user"
        assert "Go 백엔드" in f.body

    @pytest.mark.asyncio
    async def test_raises_file_not_found_when_missing(self):
        store, bucket = _store()
        bucket.blob.return_value = _blob(None)
        with pytest.raises(FileNotFoundError):
            await store.load_file(USER_ID, "missing.md")


class TestSaveFile:
    @pytest.mark.asyncio
    async def test_uploads_serialized_md(self):
        store, bucket = _store()
        blob = _blob()
        bucket.blob.return_value = blob
        f = MemoryFile(filename="role.md", name="role", description="설명", memory_type="user", body="내용")
        await store.save_file(USER_ID, f)
        blob.upload_from_string.assert_called_once()
        uploaded = blob.upload_from_string.call_args[0][0].decode()
        assert "role" in uploaded
        assert "내용" in uploaded

    @pytest.mark.asyncio
    async def test_blob_key_uses_filename(self):
        store, bucket = _store()
        bucket.blob.return_value = _blob()
        f = MemoryFile(filename="my_file.md", name="n", description="d", memory_type="feedback", body="b")
        await store.save_file(USER_ID, f)
        bucket.blob.assert_called_with(f"users/{USER_ID}/my_file.md")


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_deletes_blob(self):
        store, bucket = _store()
        blob = MagicMock()
        bucket.blob.return_value = blob
        await store.delete_file(USER_ID, "role.md")
        blob.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_removes_from_cache(self):
        store, bucket = _store()
        store._cache[USER_ID] = {"role.md": b"data"}
        bucket.blob.return_value = MagicMock()
        await store.delete_file(USER_ID, "role.md")
        assert "role.md" not in store._cache.get(USER_ID, {})

    @pytest.mark.asyncio
    async def test_no_error_when_blob_missing(self):
        store, bucket = _store()
        blob = MagicMock()
        blob.delete.side_effect = Exception("not found")
        bucket.blob.return_value = blob
        await store.delete_file(USER_ID, "missing.md")


class TestLoadEmbedding:
    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        store, bucket = _store()
        bucket.blob.return_value = _blob(None)
        result = await store.load_embedding(USER_ID, "role")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_vector(self):
        store, bucket = _store()
        data = json.dumps({"embedding": [0.1, 0.2, 0.3]}).encode()
        bucket.blob.return_value = _blob(data)
        result = await store.load_embedding(USER_ID, "role")
        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_uses_emb_json_key(self):
        store, bucket = _store()
        bucket.blob.return_value = _blob(None)
        await store.load_embedding(USER_ID, "my_skill")
        bucket.blob.assert_called_with(f"users/{USER_ID}/my_skill.emb.json")


class TestSaveEmbedding:
    @pytest.mark.asyncio
    async def test_uploads_json(self):
        store, bucket = _store()
        blob = _blob()
        bucket.blob.return_value = blob
        await store.save_embedding(USER_ID, "role", [0.1, 0.2])
        uploaded = json.loads(blob.upload_from_string.call_args[0][0])
        assert uploaded["embedding"] == [0.1, 0.2]


class TestCleanup:
    @pytest.mark.asyncio
    async def test_clears_cache(self):
        store, bucket = _store()
        store._cache[USER_ID] = {"file.md": b"data"}
        await store.cleanup(USER_ID)
        assert USER_ID not in store._cache

    @pytest.mark.asyncio
    async def test_idempotent_when_no_cache(self):
        store, _ = _store()
        await store.cleanup(USER_ID)


class TestEnvFallback:
    def test_reads_gcs_personal_bucket_env(self):
        with patch.dict("os.environ", {"GCS_PERSONAL_BUCKET": "env-bucket"}):
            assert GCSMemoryStore()._bucket_name == "env-bucket"

    def test_constructor_arg_takes_priority(self):
        with patch.dict("os.environ", {"GCS_PERSONAL_BUCKET": "env-bucket"}):
            assert GCSMemoryStore(bucket_name="explicit")._bucket_name == "explicit"


class TestUpdatedAt:
    def test_parse_md_file_reads_updated_at(self):
        """frontmatter에 updated_at이 있으면 파싱해서 반환."""
        f = _parse_md_file("user_role.md", _SKILL_MD_WITH_UPDATED_AT)
        expected = datetime(2026, 5, 21, 10, 0, 0, tzinfo=timezone.utc)
        assert f.updated_at == expected

    def test_parse_md_file_no_updated_at_returns_epoch(self):
        """frontmatter에 updated_at이 없으면 epoch(1970-01-01) 반환."""
        f = _parse_md_file("user_role.md", _SKILL_MD)
        assert f.updated_at == datetime(1970, 1, 1, tzinfo=timezone.utc)

    def test_parse_md_file_no_frontmatter_uses_default(self):
        """frontmatter 없는 파일은 updated_at 기본값(현재 시각)을 사용."""
        before = datetime.now(timezone.utc)
        f = _parse_md_file("plain.md", "그냥 텍스트")
        after = datetime.now(timezone.utc)
        assert before <= f.updated_at <= after

    def test_serialize_md_file_includes_updated_at(self):
        """직렬화 결과에 updated_at이 포함됨."""
        dt = datetime(2026, 5, 21, 10, 0, 0, tzinfo=timezone.utc)
        f = MemoryFile(
            filename="role.md",
            name="role",
            description="설명",
            memory_type="user",
            body="내용",
            updated_at=dt,
        )
        serialized = _serialize_md_file(f)
        assert "updated_at:" in serialized
        assert "2026-05-21" in serialized

    def test_roundtrip_preserves_updated_at(self):
        """직렬화 → 역직렬화 시 updated_at이 보존됨."""
        dt = datetime(2026, 5, 21, 10, 0, 0, tzinfo=timezone.utc)
        f = MemoryFile(
            filename="role.md",
            name="role",
            description="설명",
            memory_type="user",
            body="내용",
            updated_at=dt,
        )
        serialized = _serialize_md_file(f)
        parsed = _parse_md_file("role.md", serialized)
        assert parsed.updated_at == dt
