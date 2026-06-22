"""GCSMemoryStore 통합 테스트 — 실제 GCS 버킷 연결.

실행 전제:
    GOOGLE_APPLICATION_CREDENTIALS 환경변수에 SA JSON 경로 설정 필요.
    GCS_PERSONAL_BUCKET=<GCS_BUCKET_DEV>

실행:
    $env:GOOGLE_APPLICATION_CREDENTIALS = "path/to/sa.json"
    pytest modules/ai_agent/tests/integration/adapters/test_gcs_memory_store_integration.py -v
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

BUCKET_NAME = "<GCS_BUCKET_DEV>"
REQUIRES_GCS = pytest.mark.skipif(
    not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    reason="GOOGLE_APPLICATION_CREDENTIALS 미설정 — SA JSON 필요",
)


@pytest.fixture(scope="module")
def store():
    from ai_agent.adapters.memory.gcs_memory_store import GCSMemoryStore
    return GCSMemoryStore(bucket_name=BUCKET_NAME)


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture(autouse=True)
def cleanup_gcs_blobs(store, user_id):
    yield
    try:
        bucket = store._get_bucket()
        for blob in list(bucket.list_blobs(prefix=f"users/{user_id}/")):
            blob.delete()
    except Exception:
        pass


@REQUIRES_GCS
class TestGCSMemoryStoreIntegration:

    @pytest.mark.asyncio
    async def test_save_and_load_index(self, store, user_id):
        from ai_agent.domain.entities.memory_file import MemoryFileRef

        refs = [
            MemoryFileRef(name="my_role", filename="my_role.md", description="역할 정보"),
            MemoryFileRef(name="feedback_style", filename="feedback_style.md", description="피드백 스타일"),
        ]
        await store.save_index(user_id, refs)
        result = await store.load_index(user_id)

        assert len(result) == 2
        assert result[0].name == "my_role"
        assert result[0].filename == "my_role.md"
        assert result[1].name == "feedback_style"

    @pytest.mark.asyncio
    async def test_load_index_returns_empty_for_new_user(self, store):
        fresh_user = uuid.uuid4()
        result = await store.load_index(fresh_user)
        assert result == []

    @pytest.mark.asyncio
    async def test_save_and_load_file(self, store, user_id):
        from ai_agent.domain.entities.memory_file import MemoryFile

        file = MemoryFile(
            filename="my_role.md",
            name="my_role",
            description="데이터 엔지니어",
            memory_type="user",
            body="Go 백엔드 전문가입니다",
        )
        await store.save_file(user_id, file)
        loaded = await store.load_file(user_id, "my_role.md")

        assert loaded.name == "my_role"
        assert loaded.memory_type == "user"
        assert loaded.description == "데이터 엔지니어"
        assert "Go 백엔드" in loaded.body

    @pytest.mark.asyncio
    async def test_load_file_raises_for_missing(self, store, user_id):
        with pytest.raises(FileNotFoundError):
            await store.load_file(user_id, "nonexistent.md")

    @pytest.mark.asyncio
    async def test_overwrite_file(self, store, user_id):
        from ai_agent.domain.entities.memory_file import MemoryFile

        file_v1 = MemoryFile(
            filename="pref.md",
            name="pref",
            description="v1",
            memory_type="feedback",
            body="원래 내용",
        )
        await store.save_file(user_id, file_v1)

        file_v2 = MemoryFile(
            filename="pref.md",
            name="pref",
            description="v2",
            memory_type="feedback",
            body="업데이트된 내용",
        )
        await store.save_file(user_id, file_v2)

        loaded = await store.load_file(user_id, "pref.md")
        assert loaded.description == "v2"
        assert "업데이트된 내용" in loaded.body

    @pytest.mark.asyncio
    async def test_save_and_load_embedding(self, store, user_id):
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        await store.save_embedding(user_id, "my_role", embedding)
        loaded = await store.load_embedding(user_id, "my_role")

        assert loaded is not None
        assert len(loaded) == 5
        assert abs(loaded[0] - 0.1) < 1e-6

    @pytest.mark.asyncio
    async def test_load_embedding_returns_none_for_missing(self, store, user_id):
        result = await store.load_embedding(user_id, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_full_flow(self, store, user_id):
        """index 저장 → file 저장 → index 재확인 → cleanup 전체 흐름."""
        from ai_agent.domain.entities.memory_file import MemoryFile, MemoryFileRef

        refs = [MemoryFileRef(name="my_role", filename="my_role.md", description="역할 정보")]
        await store.save_index(user_id, refs)

        file = MemoryFile(
            filename="my_role.md",
            name="my_role",
            description="역할 정보",
            memory_type="user",
            body="데이터 엔지니어",
        )
        await store.save_file(user_id, file)

        index = await store.load_index(user_id)
        loaded_file = await store.load_file(user_id, "my_role.md")

        assert len(index) == 1
        assert index[0].name == "my_role"
        assert "데이터 엔지니어" in loaded_file.body

        await store.cleanup(user_id)
        # cleanup 후 캐시 비워졌는지 확인 (GCS에서 다시 읽어야 함)
        index_after = await store.load_index(user_id)
        assert len(index_after) == 1
