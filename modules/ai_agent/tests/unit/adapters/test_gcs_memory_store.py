"""Unit tests for GCSMemoryStore — GCS 클라이언트를 mock하여 순수 로직만 검증."""
from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from ai_agent.adapters.memory.gcs_memory_store import GCSMemoryStore
from ai_agent.domain.entities.personal_skill import PersonalSkill

USER_ID = UUID("00000000-0000-0000-0000-000000000001")

SKILL_MD = textwrap.dedent("""\
    ---
    name: my_role
    description: 데이터 엔지니어
    type: user
    updated_at: 2026-05-13T00:00:00+00:00
    ---
    Go 백엔드 전문가입니다
""")


def _make_blob(name: str, text: str) -> MagicMock:
    blob = MagicMock()
    blob.name = name
    blob.exists.return_value = True
    blob.download_as_text.return_value = text
    return blob


def _store_with_mock_bucket() -> tuple[GCSMemoryStore, MagicMock]:
    store = GCSMemoryStore(bucket_name="test-bucket")
    bucket = MagicMock()
    store._bucket = bucket
    return store, bucket


class TestLoadIndex:
    @pytest.mark.asyncio
    async def test_returns_empty_string_when_blob_missing(self):
        store, bucket = _store_with_mock_bucket()
        blob = MagicMock()
        blob.exists.return_value = False
        bucket.blob.return_value = blob

        result = await store.load_index(USER_ID)
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_content_when_blob_exists(self):
        store, bucket = _store_with_mock_bucket()
        blob = _make_blob(f"users/{USER_ID}/MEMORY.md", "# Index\n- entry1")
        bucket.blob.return_value = blob

        result = await store.load_index(USER_ID)
        assert result == "# Index\n- entry1"

    @pytest.mark.asyncio
    async def test_blob_key_uses_correct_path(self):
        store, bucket = _store_with_mock_bucket()
        blob = MagicMock()
        blob.exists.return_value = False
        bucket.blob.return_value = blob

        await store.load_index(USER_ID)
        bucket.blob.assert_called_once_with(f"users/{USER_ID}/MEMORY.md")


class TestSaveIndex:
    @pytest.mark.asyncio
    async def test_uploads_utf8_markdown(self):
        store, bucket = _store_with_mock_bucket()
        blob = MagicMock()
        bucket.blob.return_value = blob

        await store.save_index(USER_ID, "# Index")
        blob.upload_from_string.assert_called_once_with(
            "# Index".encode("utf-8"), content_type="text/markdown"
        )


class TestLoadEntry:
    @pytest.mark.asyncio
    async def test_parses_frontmatter_correctly(self):
        store, bucket = _store_with_mock_bucket()
        blob = _make_blob(f"users/{USER_ID}/my_role.md", SKILL_MD)
        bucket.blob.return_value = blob

        skill = await store.load_entry(USER_ID, "my_role")

        assert skill.name == "my_role"
        assert skill.description == "데이터 엔지니어"
        assert skill.skill_type == "user"
        assert "Go 백엔드" in skill.body
        assert skill.user_id == USER_ID

    @pytest.mark.asyncio
    async def test_updated_at_is_tz_aware(self):
        store, bucket = _store_with_mock_bucket()
        blob = _make_blob(f"users/{USER_ID}/my_role.md", SKILL_MD)
        bucket.blob.return_value = blob

        skill = await store.load_entry(USER_ID, "my_role")
        assert skill.updated_at.tzinfo is not None


class TestSaveEntry:
    @pytest.mark.asyncio
    async def test_serializes_frontmatter_and_uploads(self):
        store, bucket = _store_with_mock_bucket()
        blob = MagicMock()
        bucket.blob.return_value = blob

        skill = PersonalSkill(
            user_id=USER_ID,
            skill_type="feedback",
            name="pref",
            description="선호도",
            body="슬랙 알림 선호",
            updated_at=datetime(2026, 5, 13, 0, 0, 0, tzinfo=timezone.utc),
        )
        await store.save_entry(USER_ID, skill)

        blob.upload_from_string.assert_called_once()
        uploaded_bytes: bytes = blob.upload_from_string.call_args[0][0]
        uploaded_text = uploaded_bytes.decode("utf-8")
        assert "pref" in uploaded_text
        assert "feedback" in uploaded_text
        assert "슬랙 알림 선호" in uploaded_text

    @pytest.mark.asyncio
    async def test_blob_key_uses_skill_name(self):
        store, bucket = _store_with_mock_bucket()
        blob = MagicMock()
        bucket.blob.return_value = blob

        skill = PersonalSkill(
            user_id=USER_ID,
            skill_type="user",
            name="my_skill",
            description="desc",
            body="body",
        )
        await store.save_entry(USER_ID, skill)
        bucket.blob.assert_called_once_with(f"users/{USER_ID}/my_skill.md")


class TestListEntries:
    @pytest.mark.asyncio
    async def test_skips_memory_md_and_non_md_files(self):
        store, bucket = _store_with_mock_bucket()
        blobs = [
            _make_blob(f"users/{USER_ID}/MEMORY.md", "# Index"),
            _make_blob(f"users/{USER_ID}/some.txt", "ignored"),
            _make_blob(f"users/{USER_ID}/pref.md", SKILL_MD),
        ]
        bucket.list_blobs.return_value = blobs

        results = await store.list_entries(USER_ID)
        assert len(results) == 1
        assert results[0].name == "my_role"

    @pytest.mark.asyncio
    async def test_returns_all_skill_entries(self):
        store, bucket = _store_with_mock_bucket()
        skills_md = [
            textwrap.dedent(f"""\
                ---
                name: skill_{stype}
                description: desc
                type: {stype}
                updated_at: 2026-05-13T00:00:00+00:00
                ---
                body
            """)
            for stype in ("user", "feedback", "project", "reference")
        ]
        blobs = [
            _make_blob(f"users/{USER_ID}/skill_{stype}.md", md)
            for stype, md in zip(
                ("user", "feedback", "project", "reference"), skills_md
            )
        ]
        bucket.list_blobs.return_value = blobs

        results = await store.list_entries(USER_ID)
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_uses_correct_prefix(self):
        store, bucket = _store_with_mock_bucket()
        bucket.list_blobs.return_value = []

        await store.list_entries(USER_ID)
        bucket.list_blobs.assert_called_once_with(prefix=f"users/{USER_ID}/")


class TestSessionCache:
    @pytest.mark.asyncio
    async def test_list_entries_hits_gcs_only_once_on_repeated_calls(self):
        store, bucket = _store_with_mock_bucket()
        blob = _make_blob(f"users/{USER_ID}/pref.md", SKILL_MD)
        bucket.list_blobs.return_value = [blob]

        await store.list_entries(USER_ID)
        await store.list_entries(USER_ID)

        bucket.list_blobs.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_entry_updates_cache_without_gcs_read(self):
        store, bucket = _store_with_mock_bucket()
        blob_list = _make_blob(f"users/{USER_ID}/pref.md", SKILL_MD)
        bucket.list_blobs.return_value = [blob_list]
        blob_save = MagicMock()
        bucket.blob.return_value = blob_save

        await store.list_entries(USER_ID)

        new_skill = PersonalSkill(
            user_id=USER_ID,
            skill_type="feedback",
            name="new_skill",
            description="신규",
            body="내용",
        )
        await store.save_entry(USER_ID, new_skill)

        bucket.list_blobs.assert_called_once()
        result = await store.list_entries(USER_ID)
        names = {s.name for s in result}
        assert "new_skill" in names

    @pytest.mark.asyncio
    async def test_save_entry_replaces_existing_skill_in_cache(self):
        store, bucket = _store_with_mock_bucket()
        blob = _make_blob(f"users/{USER_ID}/my_role.md", SKILL_MD)
        bucket.list_blobs.return_value = [blob]
        bucket.blob.return_value = MagicMock()

        await store.list_entries(USER_ID)

        updated_skill = PersonalSkill(
            user_id=USER_ID,
            skill_type="user",
            name="my_role",
            description="업데이트된 설명",
            body="업데이트된 내용",
        )
        await store.save_entry(USER_ID, updated_skill)

        result = await store.list_entries(USER_ID)
        assert len([s for s in result if s.name == "my_role"]) == 1
        assert next(s for s in result if s.name == "my_role").description == "업데이트된 설명"


class TestEnvFallback:
    def test_reads_gcs_personal_bucket_env(self):
        with patch.dict("os.environ", {"GCS_PERSONAL_BUCKET": "env-bucket"}):
            store = GCSMemoryStore()
            assert store._bucket_name == "env-bucket"

    def test_constructor_arg_takes_priority(self):
        with patch.dict("os.environ", {"GCS_PERSONAL_BUCKET": "env-bucket"}):
            store = GCSMemoryStore(bucket_name="explicit-bucket")
            assert store._bucket_name == "explicit-bucket"
