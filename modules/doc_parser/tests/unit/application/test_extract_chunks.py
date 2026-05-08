"""
REQ-006 doc_parser — tests/unit/application/test_extract_chunks.py

ExtractChunksUseCase 유닛 테스트
Port mock 사용 — ChunkingService mock으로 로직만 검증
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from common_schemas.document import ContentBlock, DocumentBlock
from doc_parser.application.use_cases.extract_chunks import ExtractChunksUseCase
from doc_parser.domain.entities.chunk import Chunk


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_document():
    """더미 DocumentBlock"""
    return MagicMock(spec=DocumentBlock, document_id=uuid4())


@pytest.fixture
def mock_chunks(mock_document):
    """더미 Chunk 목록"""
    block = MagicMock(spec=ContentBlock)
    return [
        Chunk(
            block=block,
            chunk_index=i,
            parent_document_id=mock_document.document_id,
        )
        for i in range(3)
    ]


@pytest.fixture
def use_case(mock_chunks):
    """ExtractChunksUseCase with mock ChunkingService"""
    mock_chunking = MagicMock()
    mock_chunking.chunk.return_value = mock_chunks
    return ExtractChunksUseCase(chunking_service=mock_chunking)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_execute_returns_chunks(use_case, mock_document):
    """정상 흐름: Chunk 목록 반환"""
    chunks = use_case.execute(mock_document)

    assert isinstance(chunks, list)
    assert len(chunks) == 3


def test_chunks_have_no_importance_score(use_case, mock_document):
    """importance_score는 None — REQ-004 담당"""
    chunks = use_case.execute(mock_document)

    for chunk in chunks:
        assert chunk.importance_score is None


def test_chunks_have_no_embedding(use_case, mock_document):
    """embedding은 None — REQ-004 담당"""
    chunks = use_case.execute(mock_document)

    for chunk in chunks:
        assert chunk.embedding is None


def test_strategy_passed_to_chunking_service(mock_chunks):
    """strategy 파라미터가 ChunkingService로 전달되는지 검증"""
    mock_chunking = MagicMock()
    mock_chunking.chunk.return_value = mock_chunks

    uc = ExtractChunksUseCase(chunking_service=mock_chunking)
    mock_doc = MagicMock(spec=DocumentBlock)

    uc.execute(mock_doc, strategy="token")

    mock_chunking.chunk.assert_called_once_with(mock_doc, strategy="token")


def test_empty_chunks_returned(mock_document):
    """빈 청크 목록도 정상 반환"""
    mock_chunking = MagicMock()
    mock_chunking.chunk.return_value = []

    uc = ExtractChunksUseCase(chunking_service=mock_chunking)
    chunks = uc.execute(mock_document)

    assert chunks == []


# ── 보강 테스트 ────────────────────────────────────────────────────────────────

def test_chunk_index_sequential(use_case, mock_document):
    """청크 인덱스가 순차적인지 검증"""
    chunks = use_case.execute(mock_document)

    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_chunk_parent_document_id_matches(use_case, mock_document):
    """모든 청크의 parent_document_id가 문서 ID와 일치하는지 검증"""
    chunks = use_case.execute(mock_document)

    for chunk in chunks:
        assert chunk.parent_document_id == mock_document.document_id


@pytest.mark.parametrize("strategy", [
    "structural",
    "page",
    "token",
    "table",
    None,
])
def test_all_strategies_passed_correctly(strategy, mock_chunks):
    """모든 청킹 전략 파라미터 전달 검증"""
    mock_chunking = MagicMock()
    mock_chunking.chunk.return_value = mock_chunks

    uc = ExtractChunksUseCase(chunking_service=mock_chunking)
    mock_doc = MagicMock(spec=DocumentBlock)

    uc.execute(mock_doc, strategy=strategy)

    mock_chunking.chunk.assert_called_once_with(mock_doc, strategy=strategy)


def test_chunking_service_called_exactly_once(use_case, mock_document):
    """ChunkingService.chunk() 정확히 1번만 호출"""
    use_case.execute(mock_document)
    use_case.execute(mock_document)

    assert use_case._chunking_service.chunk.call_count == 2


def test_large_chunk_count(mock_document):
    """청크 100개 대량 반환 시 정상 처리"""
    block = MagicMock(spec=ContentBlock)
    large_chunks = [
        Chunk(
            block=block,
            chunk_index=i,
            parent_document_id=mock_document.document_id,
        )
        for i in range(100)
    ]

    mock_chunking = MagicMock()
    mock_chunking.chunk.return_value = large_chunks

    uc = ExtractChunksUseCase(chunking_service=mock_chunking)
    chunks = uc.execute(mock_document)

    assert len(chunks) == 100
    assert all(c.importance_score is None for c in chunks)
    assert all(c.embedding is None for c in chunks)