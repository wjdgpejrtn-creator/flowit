"""
REQ-006 doc_parser — adapters/parsers/hwp_parser.py

HwpParser
pyhwp(hwp5html + hwp5txt) 기반 HWP 파서

정책:
    - HWP는 hwp5html을 primary parser로 사용한다.
    - hwp5html 성공 시 HTML DOM 기반으로 문단/표/이미지 참조를 추출한다.
    - hwp5html 실패 또는 결과 품질 부족 시 hwp5txt로 fallback한다.

제한 사항 (MVP):
    - HWP 페이지 정보는 안정적으로 복원하지 못하므로 page=1 고정
    - 이미지 실제 바이너리 추출은 하지 않고 img src 참조만 block으로 남김
    - 복잡한 rowspan/colspan 표는 Markdown 변환 시 단순화될 수 있음
    - 각주/서식/레이아웃 완전 복원 불가
"""
from __future__ import annotations

import re
import subprocess
from uuid import uuid4

from bs4 import BeautifulSoup
from bs4.element import Tag

from common_schemas.document import (
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
    SourceRef,
)

from doc_parser.domain.ports.parser_port import ParserPort


class HwpParser(ParserPort):
    """HWP 파서 구현체.

    pyhwp의 hwp5html을 우선 사용하여 HWP 문서를 HTML로 변환하고,
    HTML DOM에서 문단/표/이미지 참조를 block으로 변환한다.

    hwp5html이 실패하거나 결과가 빈약하면 기존 hwp5txt 기반 텍스트 추출로 fallback한다.

    지원 MIME 타입:
        application/x-hwp

    Raises:
        RuntimeError: HWP 파서 제한 지원 실패 E0205
        RuntimeError: 파일 손상 또는 읽기 실패 E0202
    """

    MIME_TYPE = "application/x-hwp"

    def parse(self, file_path: str, file_meta: FileMeta) -> DocumentBlock:
        try:
            blocks = self._parse_with_hwp5html(file_path)

            if self._is_good_html_result(blocks):
                return DocumentBlock(
                    document_id=uuid4(),
                    file_meta=file_meta,
                    parser=ParserMeta(
                        parser_name="HwpParser",
                        parser_version="1.1.0-hwp5html",
                    ),
                    blocks=blocks,
                )

            # hwp5html은 실행됐지만 결과가 빈약하면 hwp5txt로 fallback
            blocks = self._parse_with_hwp5txt(file_path)
            return DocumentBlock(
                document_id=uuid4(),
                file_meta=file_meta,
                parser=ParserMeta(
                    parser_name="HwpParser",
                    parser_version="1.1.0-hwp5txt-fallback",
                ),
                blocks=blocks,
            )

        except Exception:
            # hwp5html 계열 실패 시 hwp5txt fallback 한 번 더 시도
            try:
                blocks = self._parse_with_hwp5txt(file_path)
                return DocumentBlock(
                    document_id=uuid4(),
                    file_meta=file_meta,
                    parser=ParserMeta(
                        parser_name="HwpParser",
                        parser_version="1.1.0-hwp5txt-fallback",
                    ),
                    blocks=blocks,
                )
            except Exception as e:
                raise RuntimeError(f"E0205: HWP 파서 제한 지원 실패 — {e}") from e

    def supports(self, mime_type: str) -> bool:
        return mime_type == self.MIME_TYPE

    # ---------------------------------------------------------------------
    # hwp5html primary path
    # ---------------------------------------------------------------------

    def _parse_with_hwp5html(self, file_path: str) -> list[ContentBlock]:
        html = self._extract_html(file_path)
        return self._html_to_blocks(html)

    def _extract_html(self, file_path: str) -> str:
        """hwp5html stdout 캡처 방식.

        PowerShell에서 확인한 redirect 방식과 동일하게 stdout을 직접 받아온다.
        --output 방식보다 stdout 방식이 더 풍부한 HTML을 반환하는 케이스가 있었다.
        """
        try:
            result = subprocess.run(
                ["hwp5html", "--html", file_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "E0205: hwp5html 변환 실패 — "
                    f"returncode={result.returncode}, stderr={result.stderr}"
                )

            html = result.stdout or ""
            if len(html.strip()) < 100:
                raise RuntimeError("E0205: hwp5html 결과가 너무 짧음")

            return html

        except FileNotFoundError:
            raise RuntimeError(
                "E0205: HWP 파서 제한 지원 실패 — hwp5html 미설치. "
                "pip install pyhwp 실행 후 재시도"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("E0202: HWP 파일 읽기 실패 — hwp5html 파싱 타임아웃")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"E0202: HWP 파일 읽기 실패 — hwp5html 오류: {e}") from e

    def _html_to_blocks(self, html: str) -> list[ContentBlock]:
        soup = BeautifulSoup(html, "html.parser")
        root = soup.body or soup

        blocks: list[ContentBlock] = []
        block_index = 0
        page_num = 1

        # table, p, img를 문서 순서대로 순회한다.
        # 단, table 내부 p는 table block에서 처리하므로 paragraph로 중복 생성하지 않는다.
        for elem in root.find_all(["table", "p", "img"], recursive=True):
            if not isinstance(elem, Tag):
                continue

            if elem.name == "table":
                table_rows = self._extract_table_rows(elem)
                if not table_rows:
                    continue

                markdown = self._table_to_markdown(table_rows)
                if not markdown.strip:
                    continue

                blocks.append(
                    ContentBlock(
                        block_id=uuid4(),
                        block_type="table",
                        content=markdown,
                        page=page_num,
                        source_ref=SourceRef(
                            page=page_num,
                            block_index=block_index,
                        ),
                    )
                )
                block_index += 1
                continue

            if elem.name == "p":
                # table 안쪽 문단은 table block에 포함되므로 중복 방지
                if elem.find_parent("table") is not None:
                    continue

                # table을 감싸는 p는 자체 paragraph로 만들지 않음
                if elem.find("table") is not None:
                    continue

                text = self._clean_text(elem.get_text(" ", strip=True))
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
                continue

            if elem.name == "img":
                # table 내부 이미지도 일단 image_reference로 남긴다.
                # 추후 bindata 추출을 붙이면 실제 이미지 경로로 확장 가능.
                src = elem.get("src", "")
                if not src:
                    continue

                content = f"[HWP image reference: {src}]"
                blocks.append(
                    ContentBlock(
                        block_id=uuid4(),
                        block_type="image",
                        content=content,
                        page=page_num,
                        source_ref=SourceRef(
                            page=page_num,
                            block_index=block_index,
                        ),
                    )
                )
                block_index += 1
                continue

        return blocks

    def _extract_table_rows(self, table_elem: Tag) -> list[list[str]]:
        rows: list[list[str]] = []

        for tr in table_elem.find_all("tr", recursive=True):
            row: list[str] = []
            for cell in tr.find_all(["th", "td"], recursive=False):
                text = self._clean_text(cell.get_text(" ", strip=True))
                row.append(text)

            if any(cell.strip() for cell in row):
                rows.append(row)

        return rows

    def _table_to_markdown(self, rows: list[list[str]]) -> str:
        if not rows:
            return ""

        max_cols = max(len(row) for row in rows)
        if max_cols <= 0:
            return ""

        normalized = [
            row + [""] * (max_cols - len(row))
            for row in rows
        ]

        header = normalized[0]
        body = normalized[1:]

        lines: list[str] = []
        lines.append("| " + " | ".join(self._escape_md_cell(cell) for cell in header) + " |")
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        for row in body:
            lines.append("| " + " | ".join(self._escape_md_cell(cell) for cell in row) + " |")

        return "\n".join(lines)

    def _escape_md_cell(self, text: str) -> str:
        text = self._clean_text(text)
        return text.replace("|", "\\|")

    def _is_good_html_result(self, blocks: list[ContentBlock]) -> bool:
        if not blocks:
            return False

        text_len = sum(len(block.content or "") for block in blocks)
        table_count = sum(1 for block in blocks if block.block_type == "table")

        # hwp5html이 table을 하나라도 잡고 본문도 어느 정도 있으면 primary로 채택
        if table_count >= 1 and text_len >= 200:
            return True

        # 표가 없어도 텍스트가 충분하면 채택
        if text_len >= 1000:
            return True

        return False

    # ---------------------------------------------------------------------
    # hwp5txt fallback path
    # ---------------------------------------------------------------------

    def _parse_with_hwp5txt(self, file_path: str) -> list[ContentBlock]:
        text = self._extract_text(file_path)
        return self._text_to_blocks(text)

    def _extract_text(self, file_path: str) -> str:
        try:
            result = subprocess.run(
                ["hwp5txt", file_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"E0205: HWP 파서 제한 지원 실패 — {result.stderr}")
            return result.stdout
        except FileNotFoundError:
            raise RuntimeError(
                "E0205: HWP 파서 제한 지원 실패 — hwp5txt 미설치. "
                "pip install pyhwp 실행 후 재시도"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("E0202: HWP 파일 읽기 실패 — hwp5txt 파싱 타임아웃")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"E0202: HWP 파일 읽기 실패 — {e}") from e

    def _text_to_blocks(self, text: str) -> list[ContentBlock]:
        blocks: list[ContentBlock] = []
        block_index = 0
        page_num = 1

        paragraphs = re.split(r"\n{2,}", text.strip())
        for para in paragraphs:
            para = self._clean_text(para)
            if not para:
                continue

            blocks.append(
                ContentBlock(
                    block_id=uuid4(),
                    block_type=self._detect_block_type(para),
                    content=para,
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
    # common helpers
    # ---------------------------------------------------------------------

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _detect_block_type(self, text: str) -> str:
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

        # HWP 보도자료/공공문서에서 자주 나오는 제목성 패턴
        if is_short and no_newline and text.startswith(("<", "〈")) and text.endswith((">", "〉")):
            return "heading"

        return "text"
