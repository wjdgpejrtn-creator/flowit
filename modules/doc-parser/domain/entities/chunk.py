"""
REQ-006 doc-parser — domain/entities/chunk.py

청킹 결과 단위 엔티티 및 청킹 전략 설정 VO
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from common_schemas.document import SourceRef


class ChunkOverlapMeta(BaseModel):
    """청크 오버랩 메타데이터.

    Attributes:
        has_overlap: 이전 청크와 오버랩 존재 여부
        overlap_tokens: 오버랩 토큰 수 (has_overlap=True 일 때만 유효)
    """

    has_overlap: bool
    overlap_tokens: Optional[int] = None


class Chunk(BaseModel):
    """청킹 결과 단위 엔티티.

    청킹 전략 우선순위:
        1순위: structural — heading 기준 섹션 분리
        2순위: page       — 페이지 단위 분리
        3순위: token      — 토큰 초과 시 재귀 분할
        4순위: table      — 표 독립 청크 (오버랩 없음)

    Attributes:
        chunk_id: 청크 고유 ID (UUID4 자동생성)
        chunk_type: 청킹 전략 유형
        content: 청크 텍스트 내용
        token_count: 토큰 수 (ChunkingService가 계산)
        source_ref: 원본 문서 출처 추적 (common_schemas.SourceRef)
        overlap_meta: 오버랩 정보 (table 타입은 항상 None)
        block_ids: 이 청크에 포함된 ContentBlock ID 목록
        importance_score: 중요도 점수 — REQ-004 AI_Agent 담당 (파서는 None)
    """

    chunk_id: UUID = Field(default_factory=uuid4)
    chunk_type: Literal["structural", "page", "token", "table"]
    content: str
    token_count: int
    source_ref: SourceRef
    overlap_meta: Optional[ChunkOverlapMeta] = None
    block_ids: list[UUID] = Field(default_factory=list)
    importance_score: Optional[float] = None  # REQ-004 AI_Agent 담당


class ChunkingStrategy(BaseModel):
    """청킹 전략 설정 VO.

    config/parser_quality.yaml 에서 로드.
    frozen=True → 생성 후 불변.

    Attributes:
        max_tokens: 청크 최대 토큰 수
        overlap_tokens: 청크 간 오버랩 토큰 수
        token_estimator_mode: 토큰 계산 방식
            tiktoken      — 외부망 환경
            char_estimate — 폐쇄망 기본값 (char × 0.7)
    """

    model_config = ConfigDict(frozen=True)

    max_tokens: int
    overlap_tokens: int
    token_estimator_mode: Literal["tiktoken", "char_estimate"]