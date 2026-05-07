"""
REQ-006 doc-parser — domain/entities/chunk.py

청킹 결과 단위 엔티티 및 청킹 전략 설정 VO
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from common_schemas.document import ContentBlock


class Chunk(BaseModel):
    """청킹 결과 단위 엔티티.

    Attributes:
        chunk_id: 청크 고유 ID (UUID4 자동생성)
        block: 청크에 해당하는 ContentBlock
        chunk_index: 문서 내 청크 순번
        parent_document_id: 원본 DocumentBlock ID
        importance_score: 중요도 점수 — REQ-004 AI_Agent 담당 (파서는 None)
        embedding: 임베딩 벡터 — REQ-004 AI_Agent 담당 (파서는 None)
    """

    chunk_id: UUID = Field(default_factory=uuid4)
    block: ContentBlock
    chunk_index: int
    parent_document_id: UUID
    importance_score: Optional[float] = None   # REQ-004 AI_Agent 담당
    embedding: Optional[list[float]] = None    # REQ-004 AI_Agent 담당


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