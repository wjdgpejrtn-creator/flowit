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
        content = "# Index\n- entry1"
        await store.save_index(user_id, content)
        result = await store.load_index(user_id)
        assert result == content

    @pytest.mark.asyncio
    async def test_load_index_returns_empty_for_new_user(self, store):
        fresh_user = uuid.uuid4()
        result = await store.load_index(fresh_user)
        assert result == ""

    @pytest.mark.asyncio
    async def test_save_and_load_entry(self, store, user_id):
        from ai_agent.domain.entities.personal_skill import PersonalSkill

        skill = PersonalSkill(
            user_id=user_id,
            skill_type="user",
            name="my_role",
            description="데이터 엔지니어",
            body="Go 백엔드 전문가입니다",
            updated_at=datetime(2026, 5, 13, 0, 0, 0, tzinfo=timezone.utc),
        )
        await store.save_entry(user_id, skill)
        loaded = await store.load_entry(user_id, "my_role")

        assert loaded.name == "my_role"
        assert loaded.skill_type == "user"
        assert loaded.description == "데이터 엔지니어"
        assert "Go 백엔드" in loaded.body
        assert loaded.updated_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_list_entries_returns_saved_skills(self, store, user_id):
        from ai_agent.domain.entities.personal_skill import PersonalSkill

        skills = [
            PersonalSkill(
                user_id=user_id,
                skill_type=stype,
                name=f"skill_{stype}",
                description=f"{stype} desc",
                body=f"{stype} body",
            )
            for stype in ("user", "feedback", "project", "reference")
        ]
        for skill in skills:
            await store.save_entry(user_id, skill)

        results = await store.list_entries(user_id)
        names = {r.name for r in results}
        assert {"skill_user", "skill_feedback", "skill_project", "skill_reference"} == names

    @pytest.mark.asyncio
    async def test_overwrite_entry(self, store, user_id):
        from ai_agent.domain.entities.personal_skill import PersonalSkill

        skill_v1 = PersonalSkill(
            user_id=user_id,
            skill_type="feedback",
            name="pref",
            description="v1",
            body="원래 내용",
        )
        await store.save_entry(user_id, skill_v1)

        skill_v2 = PersonalSkill(
            user_id=user_id,
            skill_type="feedback",
            name="pref",
            description="v2",
            body="업데이트된 내용",
        )
        await store.save_entry(user_id, skill_v2)

        loaded = await store.load_entry(user_id, "pref")
        assert loaded.description == "v2"
        assert "업데이트된 내용" in loaded.body

    @pytest.mark.asyncio
    async def test_full_flow(self, store, user_id):
        """index 저장 → entry 저장 → list → index 재확인 전체 흐름."""
        from ai_agent.domain.entities.personal_skill import PersonalSkill

        index_content = "# Memory Index\n- [my_role](my_role.md) — 역할 정보"
        await store.save_index(user_id, index_content)

        skill = PersonalSkill(
            user_id=user_id,
            skill_type="user",
            name="my_role",
            description="역할 정보",
            body="데이터 엔지니어",
        )
        await store.save_entry(user_id, skill)

        index = await store.load_index(user_id)
        entries = await store.list_entries(user_id)

        assert "my_role" in index
        assert len(entries) == 1
        assert entries[0].name == "my_role"
