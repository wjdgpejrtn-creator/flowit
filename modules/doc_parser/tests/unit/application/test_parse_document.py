"""
REQ-006 doc_parser — tests/unit/application/test_parse_document.py

ParseDocumentUseCase 유닛 테스트
Port mock 사용 — 실제 파서/파일 없이 로직만 검증
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from common_schemas.document import DocumentBlock, FileMeta
from doc_parser.application.use_cases.parse_document import ParseDocumentUseCase
from doc_parser.domain.entities.quality import QualityGateResult, QualityMetrics
from doc_parser.domain.entities.warning import WarningInfo


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_document():
    """더미 DocumentBlock"""
    return MagicMock(spec=DocumentBlock, document_id=uuid4())


@pytest.fixture
def mock_file_meta():
    """더미 FileMeta (PDF)"""
    meta = MagicMock(spec=FileMeta)
    meta.mime_type = "application/pdf"
    return meta


@pytest.fixture
def mock_quality_result():
    """더미 QualityGateResult"""
    metrics = QualityMetrics(
        korean_ratio=0.8,
        broken_char_ratio=0.0,
        blocks_per_page=5.0,
        heading_ratio=0.1,
        valid_table_ratio=1.0,
        structural_chunk_ratio=0.9,
        total_chunks=10,
        avg_tokens=150.0,
    )
    return QualityGateResult(
        quality_status="success",
        metrics=metrics,
        warnings=[],
        error_codes=[],
    )


@pytest.fixture
def use_case(mock_document, mock_quality_result):
    """ParseDocumentUseCase with mock ports"""
    mock_parser = MagicMock()
    mock_parser.supports.return_value = True
    mock_parser.parse.return_value = mock_document

    mock_normalizer = MagicMock()
    mock_normalizer.normalize_document.return_value = mock_document

    mock_pii = MagicMock()
    mock_pii.mask_document.return_value = (mock_document, [])

    mock_quality_gate = MagicMock()
    mock_quality_gate.evaluate.return_value = mock_quality_result

    return ParseDocumentUseCase(
        parsers=[mock_parser],
        normalizer=mock_normalizer,
        pii_masking_service=mock_pii,
        quality_gate=mock_quality_gate,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_execute_returns_document_and_quality(use_case, mock_file_meta):
    """정상 흐름: DocumentBlock + QualityGateResult 반환"""
    document, quality = use_case.execute("dummy/path.pdf", mock_file_meta)

    assert document is not None
    assert quality is not None
    assert quality.quality_status == "success"


def test_pipeline_order(use_case, mock_file_meta):
    """파이프라인 순서 검증: parse → normalize → pii → quality"""
    use_case.execute("dummy/path.pdf", mock_file_meta)

    use_case._parsers[0].parse.assert_called_once()
    use_case._normalizer.normalize_document.assert_called_once()
    use_case._pii.mask_document.assert_called_once()
    use_case._quality_gate.evaluate.assert_called_once()


def test_unsupported_mime_raises(mock_document, mock_quality_result):
    """지원하지 않는 MIME 타입 → ValueError (E0201)"""
    mock_parser = MagicMock()
    mock_parser.supports.return_value = False

    uc = ParseDocumentUseCase(
        parsers=[mock_parser],
        normalizer=MagicMock(),
        pii_masking_service=MagicMock(),
        quality_gate=MagicMock(),
    )

    meta = MagicMock(spec=FileMeta)
    meta.mime_type = "application/unknown"

    with pytest.raises(ValueError, match="E0201"):
        uc.execute("dummy/path.xyz", meta)


def test_parser_selection_by_mime(mock_document, mock_quality_result):
    """MIME 타입에 맞는 파서 선택 검증"""
    pdf_parser = MagicMock()
    pdf_parser.supports.side_effect = lambda m: m == "application/pdf"
    pdf_parser.parse.return_value = mock_document

    docx_parser = MagicMock()
    docx_parser.supports.side_effect = lambda m: m == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    mock_normalizer = MagicMock()
    mock_normalizer.normalize_document.return_value = mock_document
    mock_pii = MagicMock()
    mock_pii.mask_document.return_value = (mock_document, [])
    mock_quality = MagicMock()
    mock_quality.evaluate.return_value = mock_quality_result

    uc = ParseDocumentUseCase(
        parsers=[pdf_parser, docx_parser],
        normalizer=mock_normalizer,
        pii_masking_service=mock_pii,
        quality_gate=mock_quality,
    )

    meta = MagicMock(spec=FileMeta)
    meta.mime_type = "application/pdf"
    uc.execute("dummy/path.pdf", meta)

    pdf_parser.parse.assert_called_once()
    docx_parser.parse.assert_not_called()


# ── 보강 테스트 ────────────────────────────────────────────────────────────────

def test_parser_exception_propagates(mock_document, mock_quality_result):
    """파서가 RuntimeError 던지면 use case 밖으로 전파"""
    mock_parser = MagicMock()
    mock_parser.supports.return_value = True
    mock_parser.parse.side_effect = RuntimeError("E0202: 파일 손상")

    uc = ParseDocumentUseCase(
        parsers=[mock_parser],
        normalizer=MagicMock(),
        pii_masking_service=MagicMock(),
        quality_gate=MagicMock(),
    )

    meta = MagicMock(spec=FileMeta)
    meta.mime_type = "application/pdf"

    with pytest.raises(RuntimeError, match="E0202"):
        uc.execute("corrupt.pdf", meta)


def test_pii_masked_document_passed_to_quality_gate(mock_quality_result):
    """PII 마스킹된 문서가 quality gate에 전달되는지 검증"""
    original_doc = MagicMock(spec=DocumentBlock, document_id=uuid4())
    masked_doc = MagicMock(spec=DocumentBlock, document_id=uuid4())

    mock_parser = MagicMock()
    mock_parser.supports.return_value = True
    mock_parser.parse.return_value = original_doc

    mock_normalizer = MagicMock()
    mock_normalizer.normalize_document.return_value = original_doc

    mock_pii = MagicMock()
    mock_pii.mask_document.return_value = (masked_doc, [])

    mock_quality_gate = MagicMock()
    mock_quality_gate.evaluate.return_value = mock_quality_result

    uc = ParseDocumentUseCase(
        parsers=[mock_parser],
        normalizer=mock_normalizer,
        pii_masking_service=mock_pii,
        quality_gate=mock_quality_gate,
    )

    meta = MagicMock(spec=FileMeta)
    meta.mime_type = "application/pdf"
    uc.execute("dummy/path.pdf", meta)

    args, _ = mock_quality_gate.evaluate.call_args
    assert args[0] is masked_doc
    assert args[0] is not original_doc


def test_quality_status_failed_still_returns(mock_document):
    """quality_status=failed 여도 예외 없이 반환"""
    metrics = QualityMetrics(
        korean_ratio=0.0,
        broken_char_ratio=0.9,
        blocks_per_page=0.1,
        heading_ratio=0.0,
        valid_table_ratio=0.0,
        structural_chunk_ratio=0.0,
        total_chunks=0,
        avg_tokens=0.0,
    )
    failed_result = QualityGateResult(
        quality_status="failed",
        metrics=metrics,
        warnings=[],
        error_codes=["E0211"],
        decision_reason="품질 기준 미달",
    )

    mock_parser = MagicMock()
    mock_parser.supports.return_value = True
    mock_parser.parse.return_value = mock_document

    mock_normalizer = MagicMock()
    mock_normalizer.normalize_document.return_value = mock_document

    mock_pii = MagicMock()
    mock_pii.mask_document.return_value = (mock_document, [])

    mock_quality_gate = MagicMock()
    mock_quality_gate.evaluate.return_value = failed_result

    uc = ParseDocumentUseCase(
        parsers=[mock_parser],
        normalizer=mock_normalizer,
        pii_masking_service=mock_pii,
        quality_gate=mock_quality_gate,
    )

    meta = MagicMock(spec=FileMeta)
    meta.mime_type = "application/pdf"
    document, quality = uc.execute("bad_quality.pdf", meta)

    assert quality.quality_status == "failed"
    assert "E0211" in quality.error_codes
    assert document is not None


def test_pii_warnings_do_not_break_pipeline(mock_document, mock_quality_result):
    """PII 경고가 있어도 파이프라인 정상 완료 — WarningInfo 실제 VO 사용"""
    mock_parser = MagicMock()
    mock_parser.supports.return_value = True
    mock_parser.parse.return_value = mock_document

    mock_normalizer = MagicMock()
    mock_normalizer.normalize_document.return_value = mock_document

    # WarningInfo 실제 VO 인스턴스 사용 (W-2 반영)
    pii_warning_1 = WarningInfo(code="W0101", message="PII 감지: 이름")
    pii_warning_2 = WarningInfo(code="W0102", message="PII 감지: 전화번호")
    mock_pii = MagicMock()
    mock_pii.mask_document.return_value = (mock_document, [pii_warning_1, pii_warning_2])

    mock_quality_gate = MagicMock()
    mock_quality_gate.evaluate.return_value = mock_quality_result

    uc = ParseDocumentUseCase(
        parsers=[mock_parser],
        normalizer=mock_normalizer,
        pii_masking_service=mock_pii,
        quality_gate=mock_quality_gate,
    )

    meta = MagicMock(spec=FileMeta)
    meta.mime_type = "application/pdf"
    document, quality = uc.execute("pii_heavy.pdf", meta)

    assert document is not None
    assert quality.quality_status == "success"


@pytest.mark.parametrize("mime_type,expected_error", [
    ("application/unknown", "E0201"),
    ("image/jpeg", "E0201"),
    ("text/html", "E0201"),
])
def test_various_unsupported_mimes_raise_e0201(mime_type, expected_error):
    """다양한 미지원 MIME 타입 → 전부 E0201"""
    mock_parser = MagicMock()
    mock_parser.supports.return_value = False

    uc = ParseDocumentUseCase(
        parsers=[mock_parser],
        normalizer=MagicMock(),
        pii_masking_service=MagicMock(),
        quality_gate=MagicMock(),
    )

    meta = MagicMock(spec=FileMeta)
    meta.mime_type = mime_type

    with pytest.raises(ValueError, match=expected_error):
        uc.execute("dummy/file", meta)


@pytest.mark.parametrize("mime_type", [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/x-hwp",
    "application/hwp+zip",
    "text/markdown",
])
def test_all_supported_mime_types(mime_type, mock_document, mock_quality_result):
    """8종 파서 MIME 타입 전부 지원 검증"""
    mock_parser = MagicMock()
    mock_parser.supports.side_effect = lambda m: m == mime_type
    mock_parser.parse.return_value = mock_document

    mock_normalizer = MagicMock()
    mock_normalizer.normalize_document.return_value = mock_document
    mock_pii = MagicMock()
    mock_pii.mask_document.return_value = (mock_document, [])
    mock_quality = MagicMock()
    mock_quality.evaluate.return_value = mock_quality_result

    uc = ParseDocumentUseCase(
        parsers=[mock_parser],
        normalizer=mock_normalizer,
        pii_masking_service=mock_pii,
        quality_gate=mock_quality,
    )

    meta = MagicMock(spec=FileMeta)
    meta.mime_type = mime_type
    document, quality = uc.execute("dummy/file", meta)

    assert document is not None
    mock_parser.parse.assert_called_once()
