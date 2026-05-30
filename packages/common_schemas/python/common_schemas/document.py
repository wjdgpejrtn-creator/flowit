from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import AnalysisStatus
from .types import UtcDatetime


class BBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    x1: float
    y1: float
    x2: float
    y2: float


class SheetMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    sheet_name: str
    row_count: int
    col_count: int


class ParserMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    parser_name: str
    parser_version: str
    parse_duration_ms: Optional[int] = None


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: Optional[int] = None
    section: Optional[str] = None
    block_index: Optional[int] = None
    bbox: Optional[BBox] = None
    sheet_name: Optional[str] = None
    slide_number: Optional[int] = None


class FileMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_name: str
    file_type: str
    mime_type: str
    file_size: int
    page_count: Optional[int] = None
    unit_type: Optional[str] = None
    created_at: Optional[UtcDatetime] = None
    author: Optional[str] = None
    sheet_meta: Optional[list[SheetMeta]] = None


class ContentBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    block_id: UUID
    block_type: Literal["text", "table", "image", "heading", "code"]
    content: Optional[str] = None
    table: Optional[list[list[Any]]] = None
    page: Optional[int] = None
    section_title: Optional[str] = None
    bbox: Optional[BBox] = None
    source_ref: Optional[SourceRef] = None
    token_estimate: Optional[int] = None
    importance_score: Optional[float] = None
    metadata: Optional[dict[str, Any]] = None
    is_corrupted: bool = False


class DocumentBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: UUID
    workflow_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    file_meta: FileMeta
    parser: Optional[ParserMeta] = None
    blocks: list[ContentBlock]
    vision_block_count: int = 0
    failed_block_count: int = 0
    # 분석 상태 추적 (REQ-009/REQ-007 — Celery 태스크 진행/실패 가시화).
    analysis_status: AnalysisStatus = AnalysisStatus.PENDING
    analysis_error: Optional[str] = None
    analyzed_at: Optional[UtcDatetime] = None
    # 파싱 커버리지 (QualityGate 산출 — 페이지/블록 종류별 수). 분석 완료 시 채워진다.
    # 전방 참조(ParseCoverage는 아래 정의) — 파일 끝 model_rebuild()로 해소.
    coverage: Optional["ParseCoverage"] = None


class AnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_title: str
    category: str
    summary: str
    key_points: list[str]
    confidence: float
    source_refs: list[dict[str, Any]]
    warnings: list[str]
    questions: list[str]
    prompt_version: str
    template_type: str
    few_shot_count: int


# --- 파싱 품질/청킹 (REQ-006 doc_parser SSOT, REQ-012 이관) -----------------
# doc_parser.domain.entities에서 이관 — storage/ai_agent가 경계를 넘어 공유하는 타입.


class WarningInfo(BaseModel):
    """파싱 중 발생한 경고. code는 README 에러코드(E0201 등) 기준."""

    code: str
    message: str
    detail: Optional[dict[str, Any]] = None


class QualityMetrics(BaseModel):
    """파싱 품질 측정 지표 — QualityGate.evaluate()가 계산."""

    model_config = ConfigDict(frozen=True)

    korean_ratio: float
    broken_char_ratio: float
    blocks_per_page: float
    heading_ratio: float
    valid_table_ratio: float
    structural_chunk_ratio: float
    total_chunks: int
    avg_tokens: float


class ParseCoverage(BaseModel):
    """파싱 커버리지 지표 — QualityGateResult에 포함."""

    model_config = ConfigDict(frozen=True)

    total_pages: int = 0
    parsed_pages: int = 0
    text_blocks: int = 0
    table_blocks: int = 0
    vision_blocks: int = 0
    failed_blocks: int = 0
    warnings: list[str] = Field(default_factory=list)


class QualityGateResult(BaseModel):
    """품질 게이트 판정 결과 VO.

    quality_status: success / warning / manual_correction_required / failed.
    """

    model_config = ConfigDict(frozen=True)

    quality_status: Literal[
        "success",
        "warning",
        "manual_correction_required",
        "failed",
    ]
    metrics: QualityMetrics
    warnings: list[WarningInfo]
    error_codes: list[str]
    decision_reason: Optional[str] = None
    coverage: ParseCoverage = Field(default_factory=ParseCoverage)


class Chunk(BaseModel):
    """청킹 결과 단위 엔티티. importance_score/embedding은 REQ-004 AI_Agent가 채움."""

    chunk_id: UUID = Field(default_factory=uuid4)
    block: ContentBlock
    chunk_index: int
    parent_document_id: UUID
    token_count: int = 0
    chunk_type: str = "structural"
    importance_score: Optional[float] = None
    embedding: Optional[list[float]] = None


class ChunkingStrategy(BaseModel):
    """청킹 전략 설정 VO (config/parser_quality.yaml에서 로드)."""

    model_config = ConfigDict(frozen=True)

    max_tokens: int
    overlap_tokens: int
    token_estimator_mode: Literal["tiktoken", "char_estimate"]


# ── API 응답 DTO (api_server/routers/documents.py SSOT 이관) ──────────────────

class DocumentResponse(BaseModel):
    """문서 업로드/조회 공통 응답 DTO."""

    document_id: UUID
    file_name: str
    mime_type: str
    file_size: int
    gcs_uri: str
    is_analyzed: bool
    # 분석 상태 — 프론트엔드 폴링 신호. is_analyzed는 호환성 위해 유지(completed == True).
    analysis_status: AnalysisStatus = AnalysisStatus.PENDING
    analysis_error: Optional[str] = None
    analyzed_at: Optional[UtcDatetime] = None


class DocumentBlocksResponse(BaseModel):
    """GET /api/v1/documents/{id}/blocks 응답 — 파싱 결과 본문 전용 DTO.

    DocumentResponse(메타)와 분리: 메타 폴링은 가벼운 페이로드, blocks는 분석 완료 후 1회.
    """

    document_id: UUID
    blocks: list[ContentBlock]
    analysis_status: AnalysisStatus
    analysis_error: Optional[str] = None
    analyzed_at: Optional[UtcDatetime] = None
    # 파싱 커버리지 — 분석 완료(completed) 시 채워짐. 진행중/실패 시 None.
    coverage: Optional[ParseCoverage] = None


class AnalyzeDispatchResponse(BaseModel):
    """문서 분석 Celery 태스크 디스패치 응답."""

    document_id: UUID
    task_id: str
    action: str


class DocumentDownloadResponse(BaseModel):
    """문서 다운로드 서명 URL 응답."""

    document_id: UUID
    download_url: str
    expires_in: int


# DocumentBlock.coverage가 아래에서 정의된 ParseCoverage를 전방 참조하므로 재빌드로 해소.
DocumentBlock.model_rebuild()
