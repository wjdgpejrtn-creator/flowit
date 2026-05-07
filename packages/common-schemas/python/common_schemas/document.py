from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
    created_at: Optional[datetime] = None
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


class DocumentBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: UUID
    workflow_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    file_meta: FileMeta
    parser: Optional[ParserMeta] = None
    blocks: list[ContentBlock]


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
