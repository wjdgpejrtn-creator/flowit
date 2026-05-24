from __future__ import annotations

import os
from functools import lru_cache

from skills_marketplace.domain.ports.skill_document_store import SkillDocumentStore
from storage.adapters.gcs_adapter import GCSAdapter
from storage.adapters.gcs_skill_document_store import GcsSkillDocumentStore


@lru_cache(maxsize=1)
def get_skill_document_store() -> SkillDocumentStore:
    """SkillDocumentStore (skills_marketplace Port) DI — ADR-0017 이중 저장 "지침서" 측.

    Production: GCSAdapter(`SKILLS_MARKETPLACE_BUCKET` env) — ADR-0017 §"GCS 경로 패턴"의
    스킬 마켓플레이스 전용 버킷(일반 업로드 `GCS_BUCKET_NAME`과 분리, 스킬 문서가 일반
    업로드 파일과 같은 버킷에 섞이지 않도록). 테스트는 `dependency_overrides`로 swap.
    consumer = skills_marketplace use case (박아름 후속 — `CreateDraftSkillUseCase` 등).

    ⚠️ `SKILLS_MARKETPLACE_BUCKET` 미설정 시 GCSAdapter가 `GCS_BUCKET_NAME`로 silent
    fallback — staging 배포 시 Cloud Run env 설정 필수.
    """
    return GcsSkillDocumentStore(
        object_storage=GCSAdapter(bucket_name=os.getenv("SKILLS_MARKETPLACE_BUCKET")),
    )
