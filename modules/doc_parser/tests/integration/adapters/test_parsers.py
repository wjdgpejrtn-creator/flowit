"""
REQ-006 doc_parser — tests/integration/adapters/test_parsers.py

파서 통합 테스트 (실제 파일 기반)
fixtures/ 폴더의 실제 파일로 파서 동작 검증
"""
from __future__ import annotations

from pathlib import Path

import pytest

from common_schemas.document import FileMeta

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"

SUFFIX_TO_MIME = {
    ".pdf":  "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv":  "text/csv",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".hwp":  "application/x-hwp",
    ".hwpx": "application/hwp+zip",
    ".md":   "text/markdown",
}


def make_file_meta(file_path: Path) -> FileMeta:
    return FileMeta(
        file_name=file_path.name,
        file_type=file_path.suffix.lstrip("."),
        mime_type=SUFFIX_TO_MIME[file_path.suffix.lower()],
        file_size=file_path.stat().st_size,
    )


def get_fixtures(ext: str) -> list[str]:
    """fixtures 폴더에서 확장자별 파일 자동 수집."""
    return [f.name for f in sorted(FIXTURES.glob(f"*.{ext}"))]


def print_block_summary(filename: str, blocks, include_heading: bool = False) -> None:
    """블록 요약 출력 공통 함수."""
    print(f"\n{filename} - 블록 수: {len(blocks)}")
    if include_heading:
        print(f"heading 수: {sum(1 for b in blocks if b.block_type == 'heading')}")
    print(f"table 수: {sum(1 for b in blocks if b.block_type == 'table')}")


# ──────────────────────────────────────────
# PDF
# ──────────────────────────────────────────

@pytest.mark.parametrize("filename", get_fixtures("pdf"))
def test_pdf_parser(filename):
    from doc_parser.adapters.parsers.pdf_parser import PdfParser

    file_path = FIXTURES / filename
    parser = PdfParser()
    file_meta = make_file_meta(file_path)

    is_scanned = parser.is_scanned_pdf(str(file_path))
    print(f"\n{filename} - 스캔PDF: {is_scanned}")

    if is_scanned:
        with pytest.raises(ValueError, match="E0212"):
            parser.parse(str(file_path), file_meta)
        return

    result = parser.parse(str(file_path), file_meta)
    print_block_summary(filename, result.blocks, include_heading=True)

    assert result.document_id is not None
    assert len(result.blocks) > 0


# ──────────────────────────────────────────
# DOCX
# ──────────────────────────────────────────

@pytest.mark.parametrize("filename", get_fixtures("docx"))
def test_docx_parser(filename):
    from doc_parser.adapters.parsers.docx_parser import DocxParser

    file_path = FIXTURES / filename
    parser = DocxParser()
    file_meta = make_file_meta(file_path)
    result = parser.parse(str(file_path), file_meta)

    print_block_summary(filename, result.blocks, include_heading=True)

    assert result.document_id is not None
    assert len(result.blocks) > 0


# ──────────────────────────────────────────
# XLSX
# ──────────────────────────────────────────

@pytest.mark.parametrize("filename", get_fixtures("xlsx"))
def test_xlsx_parser(filename):
    from doc_parser.adapters.parsers.xlsx_parser import XlsxParser

    file_path = FIXTURES / filename
    parser = XlsxParser()
    file_meta = make_file_meta(file_path)
    result = parser.parse(str(file_path), file_meta)

    print_block_summary(filename, result.blocks)

    assert result.document_id is not None
    assert len(result.blocks) > 0
    assert all(b.block_type == "table" for b in result.blocks)


# ──────────────────────────────────────────
# CSV
# ──────────────────────────────────────────

@pytest.mark.parametrize("filename", get_fixtures("csv"))
def test_csv_parser(filename):
    from doc_parser.adapters.parsers.csv_parser import CsvParser

    file_path = FIXTURES / filename
    parser = CsvParser()
    file_meta = make_file_meta(file_path)
    result = parser.parse(str(file_path), file_meta)

    print_block_summary(filename, result.blocks)

    assert result.document_id is not None
    assert len(result.blocks) > 0


# ──────────────────────────────────────────
# PPTX
# ──────────────────────────────────────────

@pytest.mark.parametrize("filename", get_fixtures("pptx"))
def test_pptx_parser(filename):
    from doc_parser.adapters.parsers.pptx_parser import PptxParser

    file_path = FIXTURES / filename
    parser = PptxParser()
    file_meta = make_file_meta(file_path)
    result = parser.parse(str(file_path), file_meta)

    print_block_summary(filename, result.blocks)

    assert result.document_id is not None
    assert len(result.blocks) > 0


# ──────────────────────────────────────────
# HWP
# ──────────────────────────────────────────

@pytest.mark.parametrize("filename", get_fixtures("hwp"))
def test_hwp_parser(filename):
    from doc_parser.adapters.parsers.hwp_parser import HwpParser

    file_path = FIXTURES / filename
    parser = HwpParser()
    file_meta = make_file_meta(file_path)

    try:
        result = parser.parse(str(file_path), file_meta)
        print_block_summary(filename, result.blocks)
        assert result.document_id is not None
        assert len(result.blocks) > 0
    except RuntimeError as e:
        if "E0205" in str(e):
            pytest.skip(f"HWP 제한: {e}")
        raise


# ──────────────────────────────────────────
# HWPX
# ──────────────────────────────────────────

@pytest.mark.parametrize("filename", get_fixtures("hwpx"))
def test_hwpx_parser(filename):
    from doc_parser.adapters.parsers.hwpx_parser import HwpxParser

    file_path = FIXTURES / filename
    parser = HwpxParser()
    file_meta = make_file_meta(file_path)
    result = parser.parse(str(file_path), file_meta)

    print_block_summary(filename, result.blocks)

    assert result.document_id is not None
    assert len(result.blocks) > 0


# ──────────────────────────────────────────
# Markdown
# ──────────────────────────────────────────

@pytest.mark.parametrize("filename", get_fixtures("md"))
def test_markdown_parser(filename):
    from doc_parser.adapters.parsers.markdown_parser import MarkdownParser

    file_path = FIXTURES / filename
    parser = MarkdownParser()
    file_meta = make_file_meta(file_path)
    result = parser.parse(str(file_path), file_meta)

    print_block_summary(filename, result.blocks)

    assert result.document_id is not None
    assert len(result.blocks) > 0


# ──────────────────────────────────────────
# PII 마스킹
# ──────────────────────────────────────────

def test_pii_masking_on_real_pdf():
    from doc_parser.adapters.parsers.pdf_parser import PdfParser
    from doc_parser.domain.services.pii_masking import PIIMaskingService

    file_path = FIXTURES / "sample1.pdf"
    if not file_path.exists():
        pytest.skip("sample1.pdf 없음")

    parser = PdfParser()
    file_meta = make_file_meta(file_path)

    if parser.is_scanned_pdf(str(file_path)):
        pytest.skip("스캔 PDF — 파싱 불가")

    doc = parser.parse(str(file_path), file_meta)
    svc = PIIMaskingService()
    masked_doc, warnings = svc.mask_document(doc)

    print(f"\nPII 마스킹 경고 수: {len(warnings)}")
    for w in warnings:
        print(f"  {w.code}: {w.message}")

    assert masked_doc.document_id == doc.document_id
