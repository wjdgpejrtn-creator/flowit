"""
REQ-006 doc_parser — adapters/parsers/pdf_parser.py

PdfParser
PyMuPDF(fitz) 기반 PDF 파서
스캔 PDF 감지 → E0212

처리 흐름:
    is_scanned_pdf() 먼저 실행
      → True:  E0212 + WarningInfo 반환
      → False: 본문 파싱 (fitz)
               표 파싱 (pdfplumber 보조)
               → DocumentBlock 반환
"""
from __future__ import annotations

from uuid import uuid4

import fitz  # PyMuPDF
import pdfplumber

from common_schemas.document import (
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
    SourceRef,
)

from doc_parser.domain.ports.parser_port import ParserPort


# 스캔 PDF 판단 기준 — 페이지당 최소 텍스트 길이
_SCANNED_TEXT_THRESHOLD = 30
# 스캔 판단 시 확인할 첫 N 페이지
_SCANNED_CHECK_PAGES = 3


class PdfParser(ParserPort):
    """PDF 파서 구현체.

    본문: PyMuPDF(fitz)
    표:   pdfplumber (보조)

    지원 MIME 타입:
        application/pdf

    Raises:
        ValueError: 스캔 PDF 감지 시 E0212
        RuntimeError: 파일 손상 또는 읽기 실패 E0202
    """

    MIME_TYPE = "application/pdf"

    # ──────────────────────────────────────────
    # ParserPort 구현
    # ──────────────────────────────────────────

    def parse(
        self,
        file_path: str,
        file_meta: FileMeta,
    ) -> DocumentBlock:
        """PDF 파싱 → DocumentBlock 반환.

        Args:
            file_path: PDF 파일 경로
            file_meta: 파일 메타데이터

        Returns:
            DocumentBlock: 파싱된 문서 블록

        Raises:
            ValueError: 스캔 PDF (E0212) 또는 지원하지 않는 형식 (E0201)
            RuntimeError: 파일 손상 (E0202)
        """
        try:
            # ── 1. 스캔 PDF 감지 ──
            if self.is_scanned_pdf(file_path):
                raise ValueError(
                    "E0212: OCR 필요 문서 감지 — 텍스트 기반 PDF로 변환 후 재업로드 필요"
                )

            # ── 2. 본문 파싱 (fitz) ──
            blocks: list[ContentBlock] = []
            with fitz.open(file_path) as pdf:
                page_count = len(pdf)
                for page_num, page in enumerate(pdf, start=1):
                    blocks.extend(self._parse_page(page, page_num))

            # ── 3. 표 파싱 (pdfplumber 보조) ──
            blocks.extend(self._parse_tables(file_path, existing_pages={
                b.page for b in blocks
            }))

            # ── 4. page 기준 정렬 ──
            blocks.sort(key=lambda b: (b.page or 0, b.source_ref.block_index or 0
                                       if b.source_ref else 0))

            return DocumentBlock(
                document_id=uuid4(),
                file_meta=file_meta,
                parser=ParserMeta(
                    parser_name="PdfParser",
                    parser_version="1.0.0",
                ),
                blocks=blocks,
            )

        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"E0202: PDF 파일 읽기 실패 — {e}") from e

    def supports(self, mime_type: str) -> bool:
        return mime_type == self.MIME_TYPE

    # ──────────────────────────────────────────
    # Public — 스캔 PDF 감지
    # ──────────────────────────────────────────

    def is_scanned_pdf(self, file_path: str) -> bool:
        """스캔 PDF 여부 감지.

        PyMuPDF 로 첫 _SCANNED_CHECK_PAGES 페이지 텍스트 추출 시도.
        페이지당 평균 텍스트 길이가 임계값 미만이면 스캔 PDF로 판단.

        Args:
            file_path: PDF 파일 경로

        Returns:
            bool: True → 스캔 PDF (E0212), False → 텍스트 기반 PDF
        """
        try:
            with fitz.open(file_path) as pdf:
                check_pages = min(_SCANNED_CHECK_PAGES, len(pdf))
                if check_pages == 0:
                    return True

                total_text_len = sum(
                    len(pdf[i].get_text("text").strip())
                    for i in range(check_pages)
                )
                avg_len = total_text_len / check_pages
                return avg_len < _SCANNED_TEXT_THRESHOLD

        except Exception:
            return False

    # ──────────────────────────────────────────
    # Private — 페이지 파싱
    # ──────────────────────────────────────────

    def _parse_page(
        self,
        page: fitz.Page,
        page_num: int,
    ) -> list[ContentBlock]:
        """페이지에서 ContentBlock 목록 추출.

        fitz 블록 타입:
            0 → 텍스트 블록
            1 → 이미지 블록 (MVP 제외)
        """
        blocks: list[ContentBlock] = []
        block_index = 0

        for block in page.get_text("blocks"):
            # block: (x0, y0, x1, y1, text, block_no, block_type)
            x0, y0, x1, y1, text, _, block_type = block

            if block_type != 0:  # 텍스트 블록만
                continue

            text = text.strip()
            if not text:
                continue

            block_type_str = self._detect_block_type(text)
            blocks.append(
                ContentBlock(
                    block_id=uuid4(),
                    block_type=block_type_str,
                    content=text,
                    page=page_num,
                    source_ref=SourceRef(
                        page=page_num,
                        block_index=block_index,
                    ),
                )
            )
            block_index += 1

        return blocks

    def _parse_tables(
        self,
        file_path: str,
        existing_pages: set[int],
    ) -> list[ContentBlock]:
        """pdfplumber 로 표 추출.

        Args:
            file_path: PDF 파일 경로
            existing_pages: fitz 가 이미 파싱한 페이지 번호 집합

        Returns:
            list[ContentBlock]: 표 블록 목록
        """
        table_blocks: list[ContentBlock] = []

        try:
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    tables = page.extract_tables()
                    if not tables:
                        continue

                    for table in tables:
                        if not table or not table[0]:
                            continue

                        table_blocks.append(
                            ContentBlock(
                                block_id=uuid4(),
                                block_type="table",
                                content=None,
                                page=page_num,
                                table=table,
                                source_ref=SourceRef(page=page_num),
                            )
                        )
        except Exception:
            # 표 추출 실패 → warning 으로 처리 (E0204)
            # QualityGate 가 valid_table_ratio 로 감지
            pass

        return table_blocks

    def _detect_block_type(self, text: str) -> str:
        """텍스트 내용 기반 block_type 추론.

        heading 판단 기준:
            - 줄바꿈 없음
            - 길이 50자 이하
            - 숫자·점·공백으로 시작하는 번호 패턴

        Returns:
            "heading" | "text"
        """
        import re
        text = text.strip()
        is_short = len(text) <= 50
        no_newline = "\n" not in text
        numbered = bool(re.match(r"^(\d+[\.\)]|[가-힣]\.|[IVX]+\.)\s", text))

        if is_short and no_newline and numbered:
            return "heading"
        if is_short and no_newline and text.endswith(("장", "절", "항", "조")):
            return "heading"
        return "text"