"""
REQ-006 doc-parser — tests/integration/adapters/test_parsers.py

파서 통합 테스트 (실제 파일 기반)
fixtures/ 폴더의 실제 파일로 파서 동작 검증
"""
from __future__ import annotations

from pathlib import Path

import pytest

from common_schemas.document import FileMeta

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


# ──────────────────────────────────────────
# FileMeta 픽스처
# ──────────────────────────────────────────

def make_file_meta(file_path: Path) -> FileMeta:
    suffix_to_mime = {
        ".pdf":  "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return FileMeta(
        file_name=file_path.name,
        file_type=file_path.suffix.lstrip("."),
        mime_type=suffix_to_mime[file_path.suffix],
        file_size=file_path.stat().st_size,
    )


# ──────────────────────────────────────────
# PDF 파서 테스트
# ──────────────────────────────────────────

@pytest.mark.parametrize("filename", [
    "sample1.pdf",
    "sample2.pdf",
    "sample3.pdf",
    "sample4.pdf",
    "sample5.pdf",
])
def test_pdf_parser(filename):
    """PDF 파서 — 실제 파일 파싱 및 블록 추출 확인."""
    from doc_parser.adapters.parsers.pdf_parser import PdfParser

    file_path = FIXTURES / filename
    if not file_path.exists():
        pytest.skip(f"{filename} 없음")

    parser = PdfParser()
    file_meta = make_file_meta(file_path)

    # 스캔 PDF 여부 먼저 확인
    is_scanned = parser.is_scanned_pdf(str(file_path))
    print(f"\n{filename} — 스캔PDF: {is_scanned}")

    if is_scanned:
        with pytest.raises(ValueError, match="E0212"):
            parser.parse(str(file_path), file_meta)
        return

    result = parser.parse(str(file_path), file_meta)

    print(f"블록 수: {len(result.blocks)}")
    print(f"heading 수: {sum(1 for b in result.blocks if b.block_type == 'heading')}")
    print(f"table 수: {sum(1 for b in result.blocks if b.block_type == 'table')}")

    assert result.document_id is not None
    assert len(result.blocks) > 0


# ──────────────────────────────────────────
# DOCX 파서 테스트
# ──────────────────────────────────────────

def test_docx_parser():
    """DOCX 파서 — 실제 파일 파싱 및 블록 추출 확인."""
    from doc_parser.adapters.parsers.docx_parser import DocxParser

    file_path = FIXTURES / "sample.docx"
    if not file_path.exists():
        pytest.skip("sample.docx 없음")

    parser = DocxParser()
    file_meta = make_file_meta(file_path)
    result = parser.parse(str(file_path), file_meta)

    print(f"\nsample.docx — 블록 수: {len(result.blocks)}")
    print(f"heading 수: {sum(1 for b in result.blocks if b.block_type == 'heading')}")

    assert result.document_id is not None
    assert len(result.blocks) > 0


# ──────────────────────────────────────────
# XLSX 파서 테스트
# ──────────────────────────────────────────

def test_xlsx_parser():
    """XLSX 파서 — 실제 파일 파싱 및 테이블 블록 확인."""
    from doc_parser.adapters.parsers.xlsx_parser import XlsxParser

    file_path = FIXTURES / "sample.xlsx"
    if not file_path.exists():
        pytest.skip("sample.xlsx 없음")

    parser = XlsxParser()
    file_meta = make_file_meta(file_path)
    result = parser.parse(str(file_path), file_meta)

    print(f"\nsample.xlsx — 블록 수: {len(result.blocks)}")
    print(f"시트 수: {len(result.file_meta.sheet_meta or [])}")

    assert result.document_id is not None
    assert len(result.blocks) > 0
    assert all(b.block_type == "table" for b in result.blocks)


# ──────────────────────────────────────────
# PII 마스킹 통합 테스트
# ──────────────────────────────────────────

def test_pii_masking_on_real_pdf():
    """실제 PDF 파싱 후 PII 마스킹 적용."""
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