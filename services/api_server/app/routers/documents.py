"""Documents 업로드/조회/분석 라우터 (REQ-006/009, 쿠쿠 doc_parser 입구).

흐름:
    1. POST /upload  — multipart 업로드 → GCS save + DB row(file_meta + user_id, blocks=[])
    2. GET /{id}     — DB 조회 + GCS presigned download URL
    3. POST /{id}/analyze — Celery task `execution_engine.analyze_document` dispatch
       (worker가 GCS download → ParsingPipeline → save UPSERT)

ADR-0017 이중 저장 패턴(skills_marketplace SKILL.md)과 별개. documents는 단일 저장
(원본 파일=GCS, 메타+blocks=DB)이고 ParsingPipeline 결과가 같은 document_id로 UPSERT(merge).

인가: POST /upload는 인증된 사용자(`PermissionSource.user_id` 기록). GET/POST analyze는
본인 소유만(`document.user_id != permission.user_id` → 403).
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID, uuid4

from celery import Celery
from common_schemas import DocumentBlock, FileMeta, PermissionSource
from common_schemas.broker_tasks import QUEUE_DEFAULT, TASK_ANALYZE_DOCUMENT
from common_schemas.exceptions import NotFoundError
from doc_parser.domain.ports.repository_port import DocumentRepositoryPort
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from storage.domain.ports.object_storage_port import ObjectStoragePort

from app.dependencies.celery_client import get_celery
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_document_repository
from app.dependencies.storage import get_documents_object_storage

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# GCS 키 패턴 — Phase A terraform 모듈 설명 + worker analyze task가 동일하게 계산.
_KEY_PREFIX = "documents"

# Upload size limit — Cloud Run api_server memory 1Gi 기준 안전 마진. env로 override.
# 본 가드 없으면 큰 파일이 `await file.read()`에서 메모리 적재되며 OOM 트리거.
_MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))  # 50MB 기본
_READ_CHUNK = 1 * 1024 * 1024  # 1MB chunks — limit 검사 단위


def _gcs_key(document_id: UUID, filename: str) -> str:
    """`documents/{id}/{filename}` — worker도 동일 함수로 다운로드 키 계산해야 정합."""
    return f"{_KEY_PREFIX}/{document_id}/{filename}"


async def _read_capped(file: UploadFile) -> bytes:
    """`UploadFile`을 chunk로 읽으며 `_MAX_UPLOAD_BYTES` 초과 시 413 raise.

    - 사전 가드: `file.size`(Content-Length 알 때)가 limit 초과면 read 전에 거부
    - defense-in-depth: chunked transfer encoding 등 size 미공개 케이스도 누적 검사
    가드 없으면 큰 파일이 한 번에 메모리로 읽혀 Cloud Run OOM (PR #197 self-review MED #3).
    """
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {_MAX_UPLOAD_BYTES} bytes)",
        )
    buf = bytearray()
    while True:
        chunk = await file.read(_READ_CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {_MAX_UPLOAD_BYTES} bytes)",
            )
    return bytes(buf)


class DocumentResponse(BaseModel):
    """업로드/조회 공통 응답. blocks/parser_meta는 큰 페이로드라 의도적으로 제외 —
    분석 결과 조회는 별도 엔드포인트(추후 PR)에서 chunks/quality_log와 함께 제공.

    `created_at`은 현재 응답에서 제외(self-review MED #4) — `DocumentMapper.to_domain`이
    ORM `created_at`을 도메인 엔티티(`DocumentBlock`)로 매핑하지 않아 GET 호출 시
    매번 `datetime.now()`로 갱신되면 클라 캐시/eTag/diff가 깨진다. 정식 노출은
    `DocumentBlock.created_at` 필드 추가(common_schemas 변경) + mapper 갱신 후 — Phase C.
    """

    document_id: UUID
    file_name: str
    mime_type: str
    file_size: int
    gcs_uri: str
    is_analyzed: bool  # blocks 비어있으면 False — analyze 미수행 / 진행 중


class AnalyzeDispatchResponse(BaseModel):
    document_id: UUID
    task_id: str
    action: str


class DocumentDownloadResponse(BaseModel):
    document_id: UUID
    download_url: str
    expires_in: int


def _to_response(document: DocumentBlock, gcs_uri: str) -> DocumentResponse:
    return DocumentResponse(
        document_id=document.document_id,
        file_name=document.file_meta.file_name,
        mime_type=document.file_meta.mime_type,
        file_size=document.file_meta.file_size,
        gcs_uri=gcs_uri,
        is_analyzed=len(document.blocks) > 0,
    )


@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    permission: PermissionSource = Depends(get_permission_source),
    object_storage: ObjectStoragePort = Depends(get_documents_object_storage),
    repo: DocumentRepositoryPort = Depends(get_document_repository),
) -> DocumentResponse:
    """업로드 처리 — GCS write → DB row 생성(blocks=[]).

    file_name이 비어 있으면 400. mime_type은 클라이언트 `content_type` 신뢰(server-side
    sniffing은 추후 — Magic 의존성 부담 + staging 단계에서 불필요).
    크기 한도(`MAX_UPLOAD_BYTES`, 기본 50MB) 초과 시 413 — OOM 가드.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    payload = await _read_capped(file)
    document_id = uuid4()
    key = _gcs_key(document_id, file.filename)
    gcs_uri = await object_storage.upload(
        key,
        payload,
        metadata={"user_id": str(permission.user_id), "uploaded_by": "api_server"},
    )

    file_meta = FileMeta(
        file_name=file.filename,
        file_type=Path(file.filename).suffix.lstrip(".").lower() or "unknown",
        mime_type=file.content_type or "application/octet-stream",
        file_size=len(payload),
    )
    document = DocumentBlock(
        document_id=document_id,
        user_id=permission.user_id,
        file_meta=file_meta,
        blocks=[],  # analyze 시 ParseDocumentUseCase가 채움 (UPSERT)
    )
    saved_id = await repo.save(document)

    return _to_response(document.model_copy(update={"document_id": saved_id}), gcs_uri)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    permission: PermissionSource = Depends(get_permission_source),
    repo: DocumentRepositoryPort = Depends(get_document_repository),
) -> DocumentResponse:
    """단건 조회 — owner만 200. 미존재 404, 타인 소유 403."""
    document = await repo.get_by_id(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    if document.user_id != permission.user_id:
        raise HTTPException(status_code=403, detail="Document belongs to another user")
    gcs_uri = f"gs://{_KEY_PREFIX}/{document_id}/{document.file_meta.file_name}"
    return _to_response(document, gcs_uri)


@router.get("/{document_id}/download", response_model=DocumentDownloadResponse)
async def get_document_download_url(
    document_id: UUID,
    permission: PermissionSource = Depends(get_permission_source),
    object_storage: ObjectStoragePort = Depends(get_documents_object_storage),
    repo: DocumentRepositoryPort = Depends(get_document_repository),
) -> DocumentDownloadResponse:
    """다운로드 presigned URL — owner만. GET /{id}와 분리(쿼리 권한 + presign 비용 격리).
    TTL 1시간. 만료 후 재요청 필요.
    """
    document = await repo.get_by_id(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    if document.user_id != permission.user_id:
        raise HTTPException(status_code=403, detail="Document belongs to another user")
    ttl = 3600
    key = _gcs_key(document_id, document.file_meta.file_name)
    url = await object_storage.presign(key, ttl=ttl)
    return DocumentDownloadResponse(document_id=document_id, download_url=url, expires_in=ttl)


@router.post("/{document_id}/analyze", response_model=AnalyzeDispatchResponse, status_code=202)
async def analyze_document(
    document_id: UUID,
    permission: PermissionSource = Depends(get_permission_source),
    repo: DocumentRepositoryPort = Depends(get_document_repository),
    celery: Celery = Depends(get_celery),
) -> AnalyzeDispatchResponse:
    """분석 dispatch — owner 검증 후 worker Celery task로 위임(202 Accepted).

    worker가 GCS download → `ParseDocumentUseCase.execute` → `repo.save(parsed)` UPSERT →
    `save_chunks` + `save_quality_log` 순으로 처리. 진행 상황은 추후 SSE/polling 채널로.
    """
    try:
        document = await repo.get_by_id(document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    if document.user_id != permission.user_id:
        raise HTTPException(status_code=403, detail="Document belongs to another user")

    async_result = celery.send_task(
        TASK_ANALYZE_DOCUMENT, args=[str(document_id)], queue=QUEUE_DEFAULT
    )
    return AnalyzeDispatchResponse(
        document_id=document_id, task_id=async_result.id, action="analyze"
    )
