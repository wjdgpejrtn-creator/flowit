"""
REQ-006 doc-parser — adapters/parsers/hwpx_parser.py

HwpxParser
ZIP + lxml 기반 HWPX 2.0 파서

처리 흐름:
    .hwpx 파일 = ZIP 압축
      → Contents/section0.xml 추출
      → lxml 파싱 → 단락/표 블록 변환

제한 사항 (MVP):
    - 복잡 표·서식 완전 복원 불가
    - 이미지 내 텍스트 제외
    - XML 파싱 실패 시 E0208 반환
"""
from __future__ import annotations

import re
import zipfile
from uuid import uuid4

from lxml import etree

from common_schemas.document import (
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
    SourceRef,
)

from doc_parser.domain.ports.parser_port import ParserPort

# HWPX 문서 본문 경로 후보
_CONTENT_CANDIDATES = [
    "Contents/section0.xml",
    "word/document.xml",
]


class HwpxParser(ParserPort):
    """HWPX 2.0 파서 구현체.

    ZIP + lxml 구조로 직접 파싱.

    지원 MIME 타입:
        application/hwp+zip

    제한 지원:
        복잡 표·서식 완전 복원 불가 (Phase 2)
        POC 검증 선행 필요

    Raises:
        RuntimeError: HWPX XML 파싱 실패 E0208
        RuntimeError: 파일 손상 또는 읽기 실패 E0202
    """

    MIME_TYPE = "application/hwp+zip"

    def parse(self, file_path: str, file_meta: FileMeta) -> DocumentBlock:
        xml_bytes = self._extract_xml(file_path)
        try:
            blocks = self._parse_xml(xml_bytes)
            return DocumentBlock(
                document_id=uuid4(),
                file_meta=file_meta,
                parser=ParserMeta(
                    parser_name="HwpxParser",
                    parser_version="1.0.0",
                ),
                blocks=blocks,
            )
        except Exception as e:
            raise RuntimeError(f"E0208: HWPX XML 파싱 실패 — {e}") from e

    def supports(self, mime_type: str) -> bool:
        return mime_type == self.MIME_TYPE

    # ──────────────────────────────────────────
    # Private
    # ──────────────────────────────────────────

    def _extract_xml(self, file_path: str) -> bytes:
        """ZIP에서 본문 XML 추출.

        Raises:
            RuntimeError: ZIP 읽기 실패 (E0202) 또는 본문 없음 (E0208)
        """
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                names = zf.namelist()

                content_path = None
                for candidate in _CONTENT_CANDIDATES:
                    if candidate in names:
                        content_path = candidate
                        break

                # section*.xml 패턴으로 폴백
                if not content_path:
                    for name in names:
                        if re.match(r"Contents/section\d+\.xml", name):
                            content_path = name
                            break

                if not content_path:
                    raise RuntimeError(
                        f"E0208: HWPX XML 파싱 실패 — 본문 파일을 찾을 수 없음. "
                        f"포함된 파일: {names}"
                    )

                return zf.read(content_path)

        except zipfile.BadZipFile as e:
            raise RuntimeError(f"E0202: HWPX 파일 읽기 실패 — {e}") from e
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"E0202: HWPX 파일 읽기 실패 — {e}") from e

    def _parse_xml(self, xml_bytes: bytes) -> list[ContentBlock]:
        """lxml → ContentBlock 목록 변환.

        단락(p) → text/heading 블록
        표(tbl)  → table 블록
        """
        blocks: list[ContentBlock] = []
        block_index = 0
        page_num = 1

        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            raise RuntimeError(f"E0208: HWPX XML 파싱 실패 — XML 형식 오류: {e}") from e

        for elem in root.iter():
            tag = etree.QName(elem.tag).localname if elem.tag else ""

            # 단락
            if tag == "p":
                text = self._extract_para_text(elem)
                if not text:
                    continue
                blocks.append(ContentBlock(
                    block_id=uuid4(),
                    block_type=self._detect_block_type(text),
                    content=text,
                    page=page_num,
                    source_ref=SourceRef(page=page_num, block_index=block_index),
                ))
                block_index += 1

            # 표
            elif tag in ("tbl", "table"):
                table_data = self._extract_table(elem)
                if not table_data:
                    continue
                blocks.append(ContentBlock(
                    block_id=uuid4(),
                    block_type="table",
                    content=None,
                    page=page_num,
                    table=table_data,
                    source_ref=SourceRef(page=page_num, block_index=block_index),
                ))
                block_index += 1

        return blocks

    def _extract_para_text(self, para_elem) -> str:
        """단락 요소에서 텍스트 추출 (lxml)."""
        texts = []
        for elem in para_elem.iter():
            tag = etree.QName(elem.tag).localname if elem.tag else ""
            if tag in ("t", "run", "r") and elem.text:
                texts.append(elem.text)
        return " ".join(texts).strip()

    def _extract_table(self, tbl_elem) -> list[list[str]]:
        """표 요소에서 행×열 데이터 추출 (lxml)."""
        rows = []
        for elem in tbl_elem.iter():
            tag = etree.QName(elem.tag).localname if elem.tag else ""
            if tag in ("tr", "row"):
                cells = []
                for cell_elem in elem.iter():
                    cell_tag = etree.QName(cell_elem.tag).localname if cell_elem.tag else ""
                    if cell_tag in ("tc", "cell") and cell_elem.text:
                        cells.append(cell_elem.text.strip())
                if cells:
                    rows.append(cells)
        return rows

    def _detect_block_type(self, text: str) -> str:
        """텍스트 패턴 기반 block_type 판단."""
        text = text.strip()
        is_short = len(text) <= 50
        no_newline = "\n" not in text
        numbered = bool(re.match(
            r"^(\d+[\.\)]|제\s*\d+\s*[조항절장]|[가-힣]\.|[IVX]+\.)\s", text
        ))
        if is_short and no_newline and numbered:
            return "heading"
        if is_short and no_newline and text.endswith(("장", "절", "항", "조")):
            return "heading"
        return "text"