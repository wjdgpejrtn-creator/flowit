"""
REQ-006 doc_parser — adapters/parsers/pdf_parser.py

PdfParser
PyMuPDF(fitz) 기반 PDF 파서 + pdfplumber 조건부 표 보조 파서

처리 흐름:
    1. is_scanned_pdf() 먼저 실행
       → True: E0212
       → False: 본문 파싱 진행

    2. 페이지 단위 interleaving 파싱
       → fitz로 해당 페이지 텍스트 블록 추출
       → fitz bbox/텍스트 패턴/선 정보 기반 table_score 계산
       → 표 후보 점수가 threshold 이상인 페이지에만 pdfplumber.extract_tables() 실행
       → 텍스트 block + table block 반환

정책:
    - fitz = canonical text source
    - pdfplumber = table candidate page에서만 보조 실행
    - table block은 table 필드와 content(Markdown) 양쪽에 저장
    - 긴 PDF에서 전체 페이지 pdfplumber 스캔을 피한다
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
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

# table_score가 이 값 이상이면 pdfplumber 호출
# threshold 8: 너무 많이 호출하지만 안전, threshold 12: 속도/품질 타협 후보, threshold 14+: 빨라지지만 표 누락 위험 커짐
_TABLE_SCORE_THRESHOLD = 12

# 너무 흔한 "표", "계", "연도", "2025" 같은 키워드는 제외
# 키워드는 단독 판단이 아니라 보조 점수로만 사용한다.
_TABLE_HINT_KEYWORDS = (
    "단위",
    "구분",
    "합계",
    "총계",
    "증감률",
    "비율",
    "순위",
    "항목",
    "금액",
    "수량",
    "평균",
    "시도",
    "지역",
    "비고",
)


class PdfParser(ParserPort):
    """PDF 파서 구현체.

    본문: PyMuPDF(fitz)
    표:   pdfplumber 보조. 단, table_score가 높은 페이지에만 실행.

    지원 MIME 타입:
        application/pdf

    Raises:
        ValueError: 스캔 PDF 감지 시 E0212
        RuntimeError: 파일 손상 또는 읽기 실패 E0202
    """

    MIME_TYPE = "application/pdf"

    def parse(
        self,
        file_path: str,
        file_meta: FileMeta,
    ) -> DocumentBlock:
        """PDF 파싱 → DocumentBlock 반환."""
        try:
            if self.is_scanned_pdf(file_path):
                raise ValueError(
                    "E0212: OCR 필요 문서 감지 — 텍스트 기반 PDF로 변환 후 재업로드 필요"
                )

            blocks: list[ContentBlock] = []

            # fitz와 pdfplumber를 동시에 열되,
            # pdfplumber.extract_tables()는 표 후보 페이지에서만 호출한다.
            with fitz.open(file_path) as fitz_pdf, pdfplumber.open(file_path) as plumber_pdf:
                page_count = len(fitz_pdf)

                for page_index in range(page_count):
                    page_num = page_index + 1
                    fitz_page = fitz_pdf[page_index]

                    page_text_blocks = self._parse_page_text_blocks(
                        page=fitz_page,
                        page_num=page_num,
                    )
                    blocks.extend(page_text_blocks)

                    page_text = "\n".join(
                        block.content for block in page_text_blocks if block.content
                    )

                    table_score = self._score_table_candidate_page(
                        page=fitz_page,
                        page_text=page_text,
                    )

                    if table_score >= _TABLE_SCORE_THRESHOLD:
                        page_table_blocks = self._parse_tables_on_page(
                            plumber_page=plumber_pdf.pages[page_index],
                            page_num=page_num,
                            start_block_index=len(page_text_blocks),
                        )
                        blocks.extend(page_table_blocks)

            blocks.sort(
                key=lambda b: (
                    b.page or 0,
                    b.source_ref.block_index
                    if b.source_ref and b.source_ref.block_index is not None
                    else 0,
                )
            )

            return DocumentBlock(
                document_id=uuid4(),
                file_meta=file_meta.model_copy(update={"page_count": page_count}),
                parser=ParserMeta(
                    parser_name="PdfParser",
                    parser_version="1.2.0-table-score",
                ),
                blocks=blocks,
            )

        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"E0202: PDF 파일 읽기 실패 — {e}") from e

    def supports(self, mime_type: str) -> bool:
        return mime_type == self.MIME_TYPE

    # ---------------------------------------------------------------------
    # Public — 스캔 PDF 감지
    # ---------------------------------------------------------------------

    def is_scanned_pdf(self, file_path: str) -> bool:
        """스캔 PDF 여부 감지."""
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
            # 손상 여부는 parse 단계에서 처리
            return False

    # ---------------------------------------------------------------------
    # Page text parsing — fitz
    # ---------------------------------------------------------------------

    def _parse_page_text_blocks(
        self,
        page: fitz.Page,
        page_num: int,
    ) -> list[ContentBlock]:
        """한 페이지의 텍스트 block 추출."""
        blocks: list[ContentBlock] = []
        block_index = 0

        for raw_block in page.get_text("blocks"):
            # raw_block: (x0, y0, x1, y1, text, block_no, block_type)
            x0, y0, x1, y1, text, _, block_type = raw_block

            if block_type != 0:
                continue

            text = self._clean_text(text)
            if not text:
                continue

            blocks.append(
                ContentBlock(
                    block_id=uuid4(),
                    block_type=self._detect_block_type(text),
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

    # ---------------------------------------------------------------------
    # Table candidate scoring — fitz 기반 점수식
    # ---------------------------------------------------------------------

    def _score_table_candidate_page(self, page: fitz.Page, page_text: str) -> int:
        """fitz 기반 표 후보 점수 계산.

        키워드 단독으로는 절대 표 후보를 확정하지 않는다.
        bbox 격자성, 숫자 패턴, 선/도형 정보, 키워드를 합산한다.

        점수 구성:
            - 텍스트 bbox 격자성
            - 숫자/퍼센트/금액 패턴 반복
            - 수평선/수직선 벡터 정보
            - 표 힌트 키워드
        """
        text_blocks = self._extract_fitz_text_blocks(page)

        if not text_blocks and not page_text.strip():
            return 0

        score = 0
        score += self._score_text_grid(text_blocks)
        score += self._score_numeric_patterns(page_text)
        score += self._score_vector_lines(page)
        score += self._score_table_keywords(page_text)

        return score

    def _extract_fitz_text_blocks(self, page: fitz.Page) -> list[dict]:
        """fitz blocks에서 텍스트 block과 bbox 추출."""
        blocks: list[dict] = []

        for raw_block in page.get_text("blocks"):
            if len(raw_block) < 7:
                continue

            x0, y0, x1, y1, text, _, block_type = raw_block

            if block_type != 0:
                continue

            text = self._clean_text(text)
            if not text:
                continue

            blocks.append(
                {
                    "x0": float(x0),
                    "y0": float(y0),
                    "x1": float(x1),
                    "y1": float(y1),
                    "text": text,
                }
            )

        return blocks

    def _score_text_grid(self, blocks: list[dict]) -> int:
        """텍스트 블록의 격자형 배치 점수.

        표 후보 특징:
            - 비슷한 y좌표에 여러 텍스트 블록이 있음 → 행 후보
            - 비슷한 x좌표가 여러 행에서 반복됨 → 열 후보
            - 짧은 텍스트/숫자 블록이 다수 존재
        """
        if len(blocks) < 6:
            return 0

        score = 0

        # 좌표를 적당히 버킷화해서 PDF 소수점/미세 오차 흡수
        y_buckets: dict[int, list[dict]] = defaultdict(list)
        x_buckets: dict[int, list[dict]] = defaultdict(list)

        for block in blocks:
            y_key = round(block["y0"] / 5) * 5
            x_key = round(block["x0"] / 10) * 10
            y_buckets[y_key].append(block)
            x_buckets[x_key].append(block)

        # 같은 y 근처에 3개 이상 텍스트 조각이 있으면 행 후보
        row_like_count = sum(1 for items in y_buckets.values() if len(items) >= 3)

        if row_like_count >= 2:
            score += 2
        if row_like_count >= 4:
            score += 2

        # 같은 x 근처가 여러 번 반복되면 열 후보
        repeated_x_count = sum(1 for items in x_buckets.values() if len(items) >= 3)

        if repeated_x_count >= 2:
            score += 2
        if repeated_x_count >= 4:
            score += 2

        short_blocks = 0
        short_numeric_blocks = 0

        for block in blocks:
            text = block["text"]
            if len(text) <= 40:
                short_blocks += 1
                if re.search(r"\d", text):
                    short_numeric_blocks += 1

        if short_numeric_blocks >= 6 and short_blocks >= 10:
            score += 2
        if short_numeric_blocks >= 10 and short_blocks >= 15:
            score += 2

        return score

    def _score_numeric_patterns(self, page_text: str) -> int:
        """숫자 패턴 반복 점수.

        표 후보 특징:
            - 숫자 토큰이 여러 개 들어간 줄이 반복됨
            - 퍼센트/금액/쉼표 숫자 같은 데이터성 토큰이 많음
        """
        text = page_text.strip()
        if not text:
            return 0

        score = 0
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        numeric_line_count = 0
        dense_numeric_line_count = 0
        total_numeric_tokens = 0

        number_pattern = r"[-+]?\d[\d,]*(?:\.\d+)?%?"

        for line in lines:
            numeric_tokens = re.findall(number_pattern, line)
            token_count = len(numeric_tokens)

            total_numeric_tokens += token_count

            if token_count >= 2:
                numeric_line_count += 1
            if token_count >= 3:
                dense_numeric_line_count += 1

        if numeric_line_count >= 3:
            score += 2
        if dense_numeric_line_count >= 2:
            score += 2
        if dense_numeric_line_count >= 4:
            score += 2
        if total_numeric_tokens >= 20:
            score += 1
        if total_numeric_tokens >= 40:
            score += 1

        # 파이프 문자 기반 텍스트 표
        pipe_lines = [line for line in lines if line.count("|") >= 2]
        if len(pipe_lines) >= 2:
            score += 4

        return score

    def _score_vector_lines(self, page: fitz.Page) -> int:
        """페이지의 선/도형 기반 표 후보 점수.

        PyMuPDF의 get_drawings()를 활용한다.
        PDF마다 선 객체가 없는 경우도 있으므로 보조 점수로만 사용한다.
        """
        score = 0

        try:
            drawings = page.get_drawings()
        except Exception:
            return 0

        horizontal_lines = 0
        vertical_lines = 0

        for drawing in drawings:
            for item in drawing.get("items", []):
                # item 예시:
                # ("l", p1, p2) line
                # ("re", rect, orientation) rectangle
                if not item:
                    continue

                op = item[0]

                if op == "l" and len(item) >= 3:
                    p1 = item[1]
                    p2 = item[2]

                    x_diff = abs(float(p1.x) - float(p2.x))
                    y_diff = abs(float(p1.y) - float(p2.y))

                    if x_diff >= 20 and y_diff <= 1.5:
                        horizontal_lines += 1
                    elif y_diff >= 20 and x_diff <= 1.5:
                        vertical_lines += 1

                elif op == "re" and len(item) >= 2:
                    # 사각형은 표 셀/테두리일 수 있으므로 양쪽 선 후보로 가산
                    horizontal_lines += 2
                    vertical_lines += 2

        if horizontal_lines >= 3 and vertical_lines >= 3:
            score += 3

        if horizontal_lines >= 6 and vertical_lines >= 6:
            score += 3

        return score

    def _score_table_keywords(self, page_text: str) -> int:
        """표 힌트 키워드 점수.

        키워드 단독으로 표 후보를 확정하지 않기 위해 최대 2점만 부여한다.
        """
        text = page_text.strip()
        if not text:
            return 0

        hit_count = sum(1 for keyword in _TABLE_HINT_KEYWORDS if keyword in text)

        if hit_count >= 3:
            return 2

        if hit_count >= 1:
            return 1

        return 0

    # ---------------------------------------------------------------------
    # Table parsing — pdfplumber
    # ---------------------------------------------------------------------

    def _parse_tables_on_page(
        self,
        plumber_page,
        page_num: int,
        start_block_index: int = 0,
    ) -> list[ContentBlock]:
        """pdfplumber로 특정 페이지의 표만 추출."""
        table_blocks: list[ContentBlock] = []

        try:
            tables = plumber_page.extract_tables()
            if not tables:
                return table_blocks

            block_index = start_block_index

            for table in tables:
                cleaned_table = self._clean_table(table)
                if not cleaned_table:
                    continue

                markdown = self._table_to_markdown(cleaned_table)
                if not markdown:
                    continue

                table_blocks.append(
                    ContentBlock(
                        block_id=uuid4(),
                        block_type="table",
                        content=markdown,
                        page=page_num,
                        table=cleaned_table,
                        source_ref=SourceRef(
                            page=page_num,
                            block_index=block_index,
                        ),
                    )
                )
                block_index += 1

        except Exception:
            # 표 추출 실패는 전체 PDF 파싱 실패로 보지 않음
            return table_blocks

        return table_blocks

    def _clean_table(self, table: list[list[str | None]]) -> list[list[str]]:
        """pdfplumber table 결과 정리."""
        cleaned: list[list[str]] = []

        for row in table:
            if not row:
                continue

            cleaned_row = [self._clean_text(cell or "") for cell in row]

            if any(cell.strip() for cell in cleaned_row):
                cleaned.append(cleaned_row)

        return cleaned

    def _table_to_markdown(self, table: list[list[str]]) -> str:
        """table list를 Markdown table로 변환."""
        if not table:
            return ""

        max_cols = max(len(row) for row in table)
        if max_cols <= 0:
            return ""

        normalized = [row + [""] * (max_cols - len(row)) for row in table]

        header = normalized[0]
        body = normalized[1:]

        lines: list[str] = []
        lines.append("| " + " | ".join(self._escape_md_cell(cell) for cell in header) + " |")
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        for row in body:
            lines.append("| " + " | ".join(self._escape_md_cell(cell) for cell in row) + " |")

        return "\n".join(lines)

    def _escape_md_cell(self, text: str) -> str:
        return self._clean_text(text).replace("|", "\\|")

    # ---------------------------------------------------------------------
    # Common helpers
    # ---------------------------------------------------------------------

    def _clean_text(self, text: str | None) -> str:
        if not text:
            return ""

        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _detect_block_type(self, text: str) -> str:
        """텍스트 내용 기반 block_type 추론."""
        text = text.strip()
        is_short = len(text) <= 80
        no_newline = "\n" not in text

        numbered = bool(
            re.match(
                r"^(\d+[\.\)]|제\s*\d+\s*[조항절장]|[가-힣]\.|[IVX]+\.)\s",
                text,
            )
        )

        if is_short and no_newline and numbered:
            return "heading"

        if is_short and no_newline and text.endswith(("장", "절", "항", "조")):
            return "heading"

        if is_short and no_newline and text.startswith(("<", "〈")) and text.endswith((">", "〉")):
            return "heading"

        return "text"
