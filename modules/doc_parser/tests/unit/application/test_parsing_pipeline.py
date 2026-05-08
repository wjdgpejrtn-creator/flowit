"""
REQ-006 doc_parser — tests/unit/application/test_parsing_pipeline.py

ParsingPipeline 유닛 테스트
Port mock 사용 — 전체 파이프라인 오케스트레이션 로직만 검증
"""
from __future__ import annotations

from unittest.mock import MagicMock, call
from uuid import uuid4

import pytest

from common_schemas.document import ContentBlock, DocumentBlock, FileMeta
from doc_parser.application.use_cases.parsing_pipeline import ParsingPipeline
from doc_parser.domain.entities.chunk import Chunk, ChunkingStrategy
from doc_parser.domain.entities.quality import QualityGateResult, QualityMetrics


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_document():
    doc = MagicMock(spec=DocumentBlock)
    doc.document_id = uuid4()
    return doc


@pytest.fixture
def mock_chunks(mock_document):
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
def mock_quality_result():
    metrics = QualityMetrics(
        korean_ratio=0.8,
        broken_char_ratio=0.0,
        blocks_per_page=5.0,
        heading_ratio=0.1,
        valid_table_ratio=1.0,
        structural_chunk_ratio=0.9,
        total_chunks=3,
        avg_tokens=150.0,
    )
    return QualityGateResult(
        quality_status="success",
        metrics=metrics,
        warnings=[],
        error_codes=[],
    )


@pytest.fixture
def mock_file_meta():
    meta = MagicMock(spec=FileMeta)
    meta.mime_type = "application/pdf"
    return meta


@pytest.fixture
def pipeline(mock_document, mock_chunks, mock_quality_result):
    """ParsingPipeline with all mock ports"""
    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_document

    mock_factory = MagicMock()
    mock_factory.get.return_value = mock_parser

    mock_normalizer = MagicMock()
    mock_normalizer.normalize_document.return_value = mock_document

    mock_pii = MagicMock()
    mock_pii.mask_document.return_value = (mock_document, [])

    mock_quality_gate = MagicMock()
    mock_quality_gate.evaluate.return_value = mock_quality_result

    mock_chunking = MagicMock()
    mock_chunking.chunk.return_value = mock_chunks

    mock_repo = MagicMock()
    mock_repo.save.return_value = mock_document.document_id

    mock_config = MagicMock()
    mock_config.load_pii_rules.return_value = []
    mock_config.load_chunking_strategy.return_value = ChunkingStrategy(
        max_tokens=512,
        overlap_tokens=50,
        token_estimator_mode="char_estimate",
    )
    mock_config.load_quality_config.return_value = MagicMock()

    return ParsingPipeline(
        parser_factory=mock_factory,
        normalization_service=mock_normalizer,
        pii_masking_service=mock_pii,
        quality_gate=mock_quality_gate,
        chunking_service=mock_chunking,
        repository=mock_repo,
        config_loader=mock_config,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_execute_returns_three_tuple(pipeline, mock_file_meta):
    """정상 흐름: (DocumentBlock, list[Chunk], QualityGateResult) 반환"""
    document, chunks, quality = pipeline.execute("dummy/path.pdf", mock_file_meta)

    assert document is not None
    assert isinstance(chunks, list)
    assert quality.quality_status == "success"


def test_pipeline_calls_all_steps(pipeline, mock_file_meta):
    """전체 파이프라인 스텝 호출 검증"""
    pipeline.execute("dummy/path.pdf", mock_file_meta)

    pipeline._factory.get.assert_called_once()
    pipeline._normalizer.normalize_document.assert_called_once()
    pipeline._pii.mask_document.assert_called_once()
    pipeline._chunking.chunk.assert_called_once()
    pipeline._quality_gate.evaluate.assert_called_once()


def test_repository_save_called(pipeline, mock_file_meta):
    """저장 메서드 3개 모두 호출 검증"""
    pipeline.execute("dummy/path.pdf", mock_file_meta)

    pipeline._repo.save.assert_called_once()
    pipeline._repo.save_chunks.assert_called_once()
    pipeline._repo.save_quality_log.assert_called_once()


def test_chunks_importance_score_none(pipeline, mock_file_meta):
    """청크 importance_score는 None — REQ-004 담당"""
    _, chunks, _ = pipeline.execute("dummy/path.pdf", mock_file_meta)

    for chunk in chunks:
        assert chunk.importance_score is None


def test_chunks_embedding_none(pipeline, mock_file_meta):
    """청크 embedding은 None — REQ-004 담당"""
    _, chunks, _ = pipeline.execute("dummy/path.pdf", mock_file_meta)

    for chunk in chunks:
        assert chunk.embedding is None


# ── 보강 테스트 ────────────────────────────────────────────────────────────────

def test_config_loader_all_methods_called(pipeline, mock_file_meta):
    """config_loader 3개 메서드 전부 호출 검증"""
    pipeline.execute("dummy/path.pdf", mock_file_meta)

    pipeline._config_loader.load_pii_rules.assert_called_once()
    pipeline._config_loader.load_chunking_strategy.assert_called_once()
    pipeline._config_loader.load_quality_config.assert_called_once()


def test_chunking_strategy_passed_to_chunking_service(mock_document, mock_chunks, mock_quality_result):
    """config에서 읽은 chunking strategy가 chunking service로 전달되는지 검증"""
    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_document

    mock_factory = MagicMock()
    mock_factory.get.return_value = mock_parser

    mock_normalizer = MagicMock()
    mock_normalizer.normalize_document.return_value = mock_document

    mock_pii = MagicMock()
    mock_pii.mask_document.return_value = (mock_document, [])

    mock_quality_gate = MagicMock()
    mock_quality_gate.evaluate.return_value = mock_quality_result

    mock_chunking = MagicMock()
    mock_chunking.chunk.return_value = mock_chunks

    mock_repo = MagicMock()
    mock_repo.save.return_value = mock_document.document_id

    strategy = ChunkingStrategy(
        max_tokens=256,
        overlap_tokens=30,
        token_estimator_mode="tiktoken",
    )
    mock_config = MagicMock()
    mock_config.load_pii_rules.return_value = []
    mock_config.load_chunking_strategy.return_value = strategy
    mock_config.load_quality_config.return_value = MagicMock()

    p = ParsingPipeline(
        parser_factory=mock_factory,
        normalization_service=mock_normalizer,
        pii_masking_service=mock_pii,
        quality_gate=mock_quality_gate,
        chunking_service=mock_chunking,
        repository=mock_repo,
        config_loader=mock_config,
    )

    meta = MagicMock(spec=FileMeta)
    meta.mime_type = "application/pdf"
    p.execute("dummy/path.pdf", meta)

    # chunking service에 strategy.token_estimator_mode 전달 검증
    mock_chunking.chunk.assert_called_once_with(mock_document, strategy="tiktoken")


def test_save_quality_log_receives_correct_document_id(pipeline, mock_file_meta, mock_document):
    """save_quality_log에 올바른 document_id 전달 검증"""
    pipeline.execute("dummy/path.pdf", mock_file_meta)

    _, kwargs_list = pipeline._repo.save_quality_log.call_args
    args, _ = pipeline._repo.save_quality_log.call_args
    assert args[1] == mock_document.document_id


def test_unsupported_mime_propagates(pipeline):
    """지원 안 되는 MIME → factory.get 에서 에러 전파"""
    pipeline._factory.get.side_effect = ValueError("E0201: 지원하지 않는 파일 형식")

    meta = MagicMock(spec=FileMeta)
    meta.mime_type = "image/jpeg"

    with pytest.raises(ValueError, match="E0201"):
        pipeline.execute("dummy/file.jpg", meta)


def test_repo_not_called_on_parse_failure(pipeline, mock_file_meta):
    """파싱 실패 시 repository 저장 메서드 호출되지 않아야 함"""
    pipeline._factory.get.return_value.parse.side_effect = RuntimeError("E0202: 파일 손상")

    with pytest.raises(RuntimeError):
        pipeline.execute("corrupt.pdf", mock_file_meta)

    pipeline._repo.save.assert_not_called()
    pipeline._repo.save_chunks.assert_not_called()
    pipeline._repo.save_quality_log.assert_not_called()


@pytest.mark.parametrize("quality_status", [
    "success",
    "warning",
    "manual_correction_required",
])
def test_pipeline_returns_all_quality_statuses(quality_status, mock_document, mock_chunks):
    """다양한 quality_status 에서도 정상 반환"""
    metrics = QualityMetrics(
        korean_ratio=0.5,
        broken_char_ratio=0.1,
        blocks_per_page=3.0,
        heading_ratio=0.05,
        valid_table_ratio=0.8,
        structural_chunk_ratio=0.7,
        total_chunks=3,
        avg_tokens=100.0,
    )

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_document

    mock_factory = MagicMock()
    mock_factory.get.return_value = mock_parser

    mock_normalizer = MagicMock()
    mock_normalizer.normalize_document.return_value = mock_document

    mock_pii = MagicMock()
    mock_pii.mask_document.return_value = (mock_document, [])

    quality_result = QualityGateResult(
        quality_status=quality_status,
        metrics=metrics,
        warnings=[],
        error_codes=[],
    )
    mock_quality_gate = MagicMock()
    mock_quality_gate.evaluate.return_value = quality_result

    mock_chunking = MagicMock()
    mock_chunking.chunk.return_value = mock_chunks

    mock_repo = MagicMock()
    mock_repo.save.return_value = mock_document.document_id

    mock_config = MagicMock()
    mock_config.load_pii_rules.return_value = []
    mock_config.load_chunking_strategy.return_value = ChunkingStrategy(
        max_tokens=512,
        overlap_tokens=50,
        token_estimator_mode="char_estimate",
    )
    mock_config.load_quality_config.return_value = MagicMock()

    p = ParsingPipeline(
        parser_factory=mock_factory,
        normalization_service=mock_normalizer,
        pii_masking_service=mock_pii,
        quality_gate=mock_quality_gate,
        chunking_service=mock_chunking,
        repository=mock_repo,
        config_loader=mock_config,
    )

    meta = MagicMock(spec=FileMeta)
    meta.mime_type = "application/pdf"
    document, chunks, quality = p.execute("dummy/path.pdf", meta)

    assert quality.quality_status == quality_status
    assert document is not None
    assert isinstance(chunks, list)