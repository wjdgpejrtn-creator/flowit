from __future__ import annotations

from functools import lru_cache

from skills_marketplace.domain.ports.skill_document_store import SkillDocumentStore
from storage.adapters.gcs_adapter import GCSAdapter
from storage.adapters.gcs_skill_document_store import GcsSkillDocumentStore


@lru_cache(maxsize=1)
def get_skill_document_store() -> SkillDocumentStore:
    """SkillDocumentStore (skills_marketplace Port) DI — ADR-0017 이중 저장 "지침서" 측.

    Production: GCSAdapter(`GCS_BUCKET_NAME` env). 테스트는 `dependency_overrides`로 swap.
    consumer = skills_marketplace use case(박아름 후속 — `CreateDraftSkillUseCase` 등) —
    본 PR은 등록만 (사전 배선).
    """
    return GcsSkillDocumentStore(object_storage=GCSAdapter())
