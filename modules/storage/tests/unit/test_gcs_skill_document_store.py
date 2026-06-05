from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from common_schemas import SkillDocument

from storage.adapters.gcs_skill_document_store import GcsSkillDocumentStore
from storage.adapters.local_storage_adapter import LocalStorageAdapter


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture
def store(storage_dir: Path) -> GcsSkillDocumentStore:
    return GcsSkillDocumentStore(object_storage=LocalStorageAdapter(base_dir=str(storage_dir)))


@pytest.mark.asyncio
async def test_save_and_load_round_trip(store: GcsSkillDocumentStore) -> None:
    skill_id = uuid4()
    doc = SkillDocument(
        skill_id=skill_id,
        name="블로그 글 요약",
        description="긴 블로그 글을 5문장 이내로 요약: 핵심 포인트만 추출.",
        instructions=(
            "## When to use\n블로그 글이 너무 길 때.\n\n"
            "## Step-by-step\n1. URL을 받는다.\n2. 본문을 추출한다.\n3. 5문장으로 요약한다."
        ),
    )
    await store.save(skill_id, doc)

    loaded = await store.load(skill_id)
    assert loaded is not None
    assert loaded.skill_id == skill_id
    assert loaded.name == doc.name
    assert loaded.description == doc.description
    assert loaded.instructions == doc.instructions


@pytest.mark.asyncio
async def test_composer_instructions_round_trip(store: GcsSkillDocumentStore, storage_dir: Path) -> None:
    """composer 지침(COMPOSER.md)이 있으면 같은 디렉토리에 저장되고 round-trip (#372)."""
    skill_id = uuid4()
    doc = SkillDocument(
        skill_id=skill_id,
        name="온보딩 가이드",
        description="신규 입사자 안내",
        instructions="## 노드측 지침\n요약 작성 방법...",
        composer_instructions="이 스킬은 LLM 노드(anthropic_chat) + Email 노드가 필수입니다.",
    )
    await store.save(skill_id, doc)

    assert (storage_dir / f"skills/{skill_id}/COMPOSER.md").exists()
    loaded = await store.load(skill_id)
    assert loaded is not None
    assert loaded.instructions == doc.instructions
    assert loaded.composer_instructions == doc.composer_instructions


@pytest.mark.asyncio
async def test_composer_md_not_written_when_empty(store: GcsSkillDocumentStore, storage_dir: Path) -> None:
    """composer_instructions 미지정 시 COMPOSER.md를 만들지 않고, load는 ""로 degrade (#372 detail 3)."""
    skill_id = uuid4()
    await store.save(
        skill_id,
        SkillDocument(skill_id=skill_id, name="x", description="y", instructions="z"),
    )
    assert not (storage_dir / f"skills/{skill_id}/COMPOSER.md").exists()
    loaded = await store.load(skill_id)
    assert loaded is not None
    assert loaded.composer_instructions == ""


@pytest.mark.asyncio
async def test_load_missing_returns_none(store: GcsSkillDocumentStore) -> None:
    assert await store.load(uuid4()) is None


@pytest.mark.asyncio
async def test_save_uses_deterministic_key(store: GcsSkillDocumentStore, storage_dir: Path) -> None:
    """키 패턴 `skills/{skill_id}/SKILL.md` 준수 — 호출부 skill_document_uri 구성과 정합."""
    skill_id = uuid4()
    await store.save(
        skill_id,
        SkillDocument(skill_id=skill_id, name="x", description="y", instructions="z"),
    )
    assert (storage_dir / f"skills/{skill_id}/SKILL.md").exists()


@pytest.mark.asyncio
async def test_save_returns_object_storage_uri(store: GcsSkillDocumentStore, storage_dir: Path) -> None:
    """save → URI 반환 — 호출부가 bucket 이름을 모른 채 `skill_document_uri`에 세팅 가능.
    LocalStorageAdapter는 `file://{path}` 반환, GCSAdapter는 `gs://{bucket}/{key}` 반환."""
    skill_id = uuid4()
    uri = await store.save(
        skill_id,
        SkillDocument(skill_id=skill_id, name="x", description="y", instructions="z"),
    )
    expected_path = storage_dir / f"skills/{skill_id}/SKILL.md"
    assert uri == f"file://{expected_path}"


@pytest.mark.asyncio
async def test_description_with_special_chars_round_trip(store: GcsSkillDocumentStore) -> None:
    """description이 콜론/줄바꿈 포함 자유 텍스트라도 YAML safe_dump/safe_load로 round-trip."""
    skill_id = uuid4()
    doc = SkillDocument(
        skill_id=skill_id,
        name="복잡한 스킬",
        description="작업: 데이터 변환\n- input: csv\n- output: json",
        instructions="body",
    )
    await store.save(skill_id, doc)
    loaded = await store.load(skill_id)
    assert loaded is not None
    assert loaded.description == doc.description


@pytest.mark.asyncio
async def test_delete_removes_skill_document(store: GcsSkillDocumentStore, storage_dir: Path) -> None:
    """save → delete → load None — DeletePersonalSkillUseCase의 orphan 정리 경로 (SKILL.md+COMPOSER.md)."""
    skill_id = uuid4()
    await store.save(
        skill_id,
        SkillDocument(
            skill_id=skill_id, name="x", description="y", instructions="z", composer_instructions="c"
        ),
    )
    assert (storage_dir / f"skills/{skill_id}/SKILL.md").exists()
    assert (storage_dir / f"skills/{skill_id}/COMPOSER.md").exists()

    await store.delete(skill_id)

    assert not (storage_dir / f"skills/{skill_id}/SKILL.md").exists()
    assert not (storage_dir / f"skills/{skill_id}/COMPOSER.md").exists()
    assert await store.load(skill_id) is None


@pytest.mark.asyncio
async def test_delete_missing_is_idempotent_via_local_adapter(store: GcsSkillDocumentStore) -> None:
    """LocalStorageAdapter.delete는 부재 키도 raise 없음 — 멱등 계약 통과."""
    await store.delete(uuid4())  # raise 없으면 성공


@pytest.mark.asyncio
async def test_delete_swallows_not_found_error_from_object_storage() -> None:
    """ObjectStoragePort.delete가 NotFoundError를 던지는 구현(GCSAdapter)에서도 멱등.
    GcsSkillDocumentStore가 NotFoundError를 catch하여 no-op 반환하는지 검증.
    """
    from common_schemas.exceptions import NotFoundError

    from storage.domain.ports.object_storage_port import ObjectStoragePort

    class _RaisingStorage(ObjectStoragePort):
        async def upload(self, key: str, data: bytes, metadata: dict[str, str]) -> str:
            return f"gs://test/{key}"

        async def download(self, key: str) -> bytes:
            raise NotFoundError(f"File not found: {key}", code="E-STORAGE-001")

        async def delete(self, key: str) -> None:
            raise NotFoundError(f"File not found: {key}", code="E-STORAGE-001")

        async def presign(self, key: str, ttl: int = 3600) -> str:
            return f"gs://test/{key}"

    await GcsSkillDocumentStore(object_storage=_RaisingStorage()).delete(uuid4())  # no raise


@pytest.mark.asyncio
async def test_instructions_with_horizontal_rule_round_trip(store: GcsSkillDocumentStore) -> None:
    """markdown `---` 가로선이 body에 있어도 frontmatter 종료 fence와 혼동되지 않는다.
    (deserializer가 첫 `\\n---\\n`을 종료 펜스로 사용 — 그 이후 `---`은 안전.)"""
    skill_id = uuid4()
    doc = SkillDocument(
        skill_id=skill_id,
        name="rule",
        description="md horizontal rule test",
        instructions="Line 1\n\n---\n\nLine 2",
    )
    await store.save(skill_id, doc)
    loaded = await store.load(skill_id)
    assert loaded is not None
    assert loaded.instructions == doc.instructions
