from __future__ import annotations

import os
from functools import lru_cache

from skills_marketplace.domain.ports.skill_document_store import SkillDocumentStore
from storage.adapters.gcs_adapter import GCSAdapter
from storage.adapters.gcs_skill_document_store import GcsSkillDocumentStore
from storage.domain.ports.object_storage_port import ObjectStoragePort


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


@lru_cache(maxsize=1)
def get_documents_object_storage() -> ObjectStoragePort:
    """일반 사용자 업로드 documents 버킷용 ObjectStoragePort DI — REQ-006/009.

    Production: GCSAdapter(`DOCUMENTS_BUCKET` env) — `infra/.../main.tf` `module.documents_bucket`이
    `${project}-documents-${env}` 이름으로 생성하고 api_server module env_vars에 주입.
    consumer: `app/routers/documents.py`의 upload(GCS write) + presign(GET 다운로드 URL).
    SkillDocumentStore와 달리 high-level wrapper 없이 raw `ObjectStoragePort`로 노출 —
    skill SKILL.md처럼 구조화된 도큐먼트가 아닌 일반 바이너리 업로드.

    ⚠️ `DOCUMENTS_BUCKET` 미설정 시 GCSAdapter가 빈 bucket name으로 fallback → upload 시
    `google.api_core.exceptions.InvalidArgument` raise. staging Cloud Run env 설정 필수
    (Phase A `feature/req-009-documents-bucket-infra` 머지+apply 후 자동 주입).
    """
    return GCSAdapter(bucket_name=os.getenv("DOCUMENTS_BUCKET"))
