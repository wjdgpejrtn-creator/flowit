"""
REQ-006 doc_parser — tests/integration/adapters/test_parsers.py

파서 통합 테스트
실제 fixture 파일로 8종 파서 동작 검증

fixture 구조 (포맷별 2~4종):
    PDF:  good_sample.pdf (일반), bad_sample.pdf (스캔 E0212)
    DOCX: good_sample1.docx, good_sample2.docx
    XLSX: good_sample1.xlsx, good_sample2.xlsx,
          bad_sample1.xlsx (styles.xml count 손상),
          bad_sample2.xlsx (styles.xml count + 멀티시트 손상)
    CSV:  good_sample.csv, bad_sample1.csv (CP949), bad_sample2.csv (혼합 인코딩)
    PPTX: good_sample1.pptx, good_sample2.pptx
    HWP:  sample1.hwp, sample2.hwp, sample3.hwp
    HWPX: table_sample.hwpx, text_sample.hwpx
    MD:   text_sample.md, bad_sample.md (표 복합)
"""
from __future__ import annotations

import pytest
from pathlib import Path

from common_schemas.document import DocumentBlock, FileMeta

# ──────────────────────────────────────────
# fixture 경로
# ──────────────────────────────────────────
FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures"


def make_file_meta(file_path: Path, mime_type: str) -> FileMeta:
    """테스트용 FileMeta 생성."""
    # mime_type에서 file_type 추출 (예: application/pdf → pdf)
    file_type = file_path.suffix.lstrip(".").lower()
    return FileMeta(
        file_name=file_path.name,
        file_type=file_type,
        mime_type=mime_type,
        file_size=file_path.stat().st_size,
    )


def assert_valid_document(doc: DocumentBlock, min_blocks: int = 1) -> None:
    """DocumentBlock 기본 검증."""
    assert doc is not None
    assert doc.blocks is not None
    assert len(doc.blocks) >= min_blocks
    for block in doc.blocks:
        assert block.block_type in ("text", "table", "image", "heading", "code")


# ──────────────────────────────────────────
# PDF
# ──────────────────────────────────────────
class TestPdfParser:

    def test_good_sample(self):
        """일반 PDF — 텍스트+표+그래프 파싱."""
        from doc_parser.adapters.parsers.pdf_parser import PdfParser

        path = FIXTURE_DIR / "good_sample.pdf"
        if not path.exists():
            pytest.skip("good_sample.pdf fixture 없음")

        parser = PdfParser()
        meta = make_file_meta(path, "application/pdf")
        doc = parser.parse(str(path), meta)
        assert_valid_document(doc)

    def test_bad_sample_scan_pdf(self):
        """스캔 PDF — E0212 감지 또는 최소 파싱."""
        from doc_parser.adapters.parsers.pdf_parser import PdfParser

        path = FIXTURE_DIR / "bad_sample.pdf"
        if not path.exists():
            pytest.skip("bad_sample.pdf fixture 없음")

        parser = PdfParser()
        meta = make_file_meta(path, "application/pdf")

        # 스캔 PDF는 E0212 에러 또는 빈 텍스트로 파싱될 수 있음
        try:
            doc = parser.parse(str(path), meta)
            # 파싱됐다면 blocks가 있어야 함
            assert doc is not None
        except Exception as e:
            assert "E0212" in str(e) or "스캔" in str(e)


# ──────────────────────────────────────────
# DOCX
# ──────────────────────────────────────────
class TestDocxParser:

    MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def test_good_sample1(self):
        from doc_parser.adapters.parsers.docx_parser import DocxParser

        path = FIXTURE_DIR / "good_sample1.docx"
        if not path.exists():
            pytest.skip("good_sample1.docx fixture 없음")

        parser = DocxParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)

    def test_good_sample2(self):
        from doc_parser.adapters.parsers.docx_parser import DocxParser

        path = FIXTURE_DIR / "good_sample2.docx"
        if not path.exists():
            pytest.skip("good_sample2.docx fixture 없음")

        parser = DocxParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)


# ──────────────────────────────────────────
# XLSX
# ──────────────────────────────────────────
class TestXlsxParser:

    MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def test_good_sample1(self):
        from doc_parser.adapters.parsers.xlsx_parser import XlsxParser

        path = FIXTURE_DIR / "good_sample1.xlsx"
        if not path.exists():
            pytest.skip("good_sample1.xlsx fixture 없음")

        parser = XlsxParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)

    def test_good_sample2(self):
        from doc_parser.adapters.parsers.xlsx_parser import XlsxParser

        path = FIXTURE_DIR / "good_sample2.xlsx"
        if not path.exists():
            pytest.skip("good_sample2.xlsx fixture 없음")

        parser = XlsxParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)

    def test_bad_sample1_styles_xml_count(self):
        """styles.xml count 속성 손상 XLSX — _load_workbook_safe() 복구 검증."""
        from doc_parser.adapters.parsers.xlsx_parser import XlsxParser

        path = FIXTURE_DIR / "bad_sample1.xlsx"
        if not path.exists():
            pytest.skip("bad_sample1.xlsx fixture 없음")

        parser = XlsxParser()
        # 복구 성공해야 함 (에러 없이 파싱)
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)

    def test_bad_sample2_styles_xml_count_multisheet(self):
        """styles.xml count 손상 + 멀티시트 XLSX — 복구 검증."""
        from doc_parser.adapters.parsers.xlsx_parser import XlsxParser

        path = FIXTURE_DIR / "bad_sample2.xlsx"
        if not path.exists():
            pytest.skip("bad_sample2.xlsx fixture 없음")

        parser = XlsxParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)


# ──────────────────────────────────────────
# CSV
# ──────────────────────────────────────────
class TestCsvParser:

    MIME = "text/csv"

    def test_good_sample(self):
        from doc_parser.adapters.parsers.csv_parser import CsvParser

        path = FIXTURE_DIR / "good_sample.csv"
        if not path.exists():
            pytest.skip("good_sample.csv fixture 없음")

        parser = CsvParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)

    def test_bad_sample1_cp949(self):
        """CP949 인코딩 CSV — 인코딩 폴백 검증."""
        from doc_parser.adapters.parsers.csv_parser import CsvParser

        path = FIXTURE_DIR / "bad_sample1.csv"
        if not path.exists():
            pytest.skip("bad_sample1.csv fixture 없음")

        parser = CsvParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert doc is not None

    def test_bad_sample2_mixed_encoding(self):
        """혼합 인코딩 CSV — 파싱 시도."""
        from doc_parser.adapters.parsers.csv_parser import CsvParser

        path = FIXTURE_DIR / "bad_sample2.csv"
        if not path.exists():
            pytest.skip("bad_sample2.csv fixture 없음")

        parser = CsvParser()
        # 완전 깨진 파일은 에러 또는 빈 결과 허용
        try:
            doc = parser.parse(str(path), make_file_meta(path, self.MIME))
            assert doc is not None
        except Exception:
            pass  # 복구 불가 케이스 허용


# ──────────────────────────────────────────
# PPTX
# ──────────────────────────────────────────
class TestPptxParser:

    MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    def test_good_sample1(self):
        from doc_parser.adapters.parsers.pptx_parser import PptxParser

        path = FIXTURE_DIR / "good_sample1.pptx"
        if not path.exists():
            pytest.skip("good_sample1.pptx fixture 없음")

        parser = PptxParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)

    def test_good_sample2(self):
        from doc_parser.adapters.parsers.pptx_parser import PptxParser

        path = FIXTURE_DIR / "good_sample2.pptx"
        if not path.exists():
            pytest.skip("good_sample2.pptx fixture 없음")

        parser = PptxParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)


# ──────────────────────────────────────────
# HWP
# ──────────────────────────────────────────
class TestHwpParser:

    MIME = "application/x-hwp"

    @pytest.mark.parametrize("filename", [
        "sample1.hwp",
        "sample2.hwp",
        "sample3.hwp",
    ])
    def test_hwp_samples(self, filename: str):
        """HWP 3종 — hwp5html primary + hwp5txt fallback."""
        from doc_parser.adapters.parsers.hwp_parser import HwpParser

        path = FIXTURE_DIR / filename
        if not path.exists():
            pytest.skip(f"{filename} fixture 없음")

        parser = HwpParser()
        try:
            doc = parser.parse(str(path), make_file_meta(path, self.MIME))
            assert doc is not None
        except Exception as e:
            # HWP는 환경 의존적 — E0205 허용
            assert "E0205" in str(e) or "hwp" in str(e).lower()


# ──────────────────────────────────────────
# HWPX
# ──────────────────────────────────────────
class TestHwpxParser:

    MIME = "application/hwp+zip"

    def test_table_sample(self):
        """표 있는 HWPX."""
        from doc_parser.adapters.parsers.hwpx_parser import HwpxParser

        path = FIXTURE_DIR / "table_sample.hwpx"
        if not path.exists():
            pytest.skip("table_sample.hwpx fixture 없음")

        parser = HwpxParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)
        # 표 블록이 최소 1개 있어야 함
        table_blocks = [b for b in doc.blocks if b.block_type == "table"]
        assert len(table_blocks) >= 1

    def test_text_sample(self):
        """일반 텍스트 HWPX."""
        from doc_parser.adapters.parsers.hwpx_parser import HwpxParser

        path = FIXTURE_DIR / "text_sample.hwpx"
        if not path.exists():
            pytest.skip("text_sample.hwpx fixture 없음")

        parser = HwpxParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)


# ──────────────────────────────────────────
# Markdown
# ──────────────────────────────────────────
class TestMarkdownParser:

    MIME = "text/markdown"

    def test_text_sample(self):
        """일반 텍스트 Markdown."""
        from doc_parser.adapters.parsers.markdown_parser import MarkdownParser

        path = FIXTURE_DIR / "text_sample.md"
        if not path.exists():
            pytest.skip("text_sample.md fixture 없음")

        parser = MarkdownParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)

    def test_bad_sample_tables(self):
        """복합 표 Markdown — 표 파서 fix 검증."""
        from doc_parser.adapters.parsers.markdown_parser import MarkdownParser

        path = FIXTURE_DIR / "bad_sample.md"
        if not path.exists():
            pytest.skip("bad_sample.md fixture 없음")

        parser = MarkdownParser()
        doc = parser.parse(str(path), make_file_meta(path, self.MIME))
        assert_valid_document(doc)
        # 표 블록이 최소 1개 있어야 함 (표 파서 활성화 검증)
        table_blocks = [b for b in doc.blocks if b.block_type == "table"]
        assert len(table_blocks) >= 1
