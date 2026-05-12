"""
REQ-006 doc_parser — adapters/parsers/markdown_parser.py

MarkdownParser
markdown-it-py 기반 Markdown 파서

처리 항목:
    - 제목(heading) / 본문(text) / 코드(code) / 표(table) 블록 구분
    - 중첩 구조 평탄화
"""
from __future__ import annotations

from uuid import uuid4

from markdown_it import MarkdownIt

from common_schemas.document import (
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
    SourceRef,
)

from doc_parser.domain.ports.parser_port import ParserPort


class MarkdownParser(ParserPort):
    """Markdown 파서 구현체.

    지원 MIME 타입:
        text/markdown

    Raises:
        RuntimeError: 파일 손상 또는 읽기 실패 E0202
        RuntimeError: 텍스트 추출 실패 E0203
    """

    MIME_TYPE = "text/markdown"

    def __init__(self) -> None:
        self._md = MarkdownIt().enable("table")

    def parse(
        self,
        file_path: str,
        file_meta: FileMeta,
    ) -> DocumentBlock:
        """Markdown 파싱 → DocumentBlock 반환.

        Args:
            file_path: Markdown 파일 경로
            file_meta: 파일 메타데이터

        Returns:
            DocumentBlock: 파싱된 문서 블록

        Raises:
            RuntimeError: 파일 읽기 실패 (E0202), 텍스트 추출 실패 (E0203)
        """
        try:
            text = self._read_file(file_path)
        except Exception as e:
            raise RuntimeError(f"E0202: Markdown 파일 읽기 실패 — {e}") from e

        try:
            blocks = self._parse_tokens(text)
            return DocumentBlock(
                document_id=uuid4(),
                file_meta=file_meta,
                parser=ParserMeta(
                    parser_name="MarkdownParser",
                    parser_version="1.0.0",
                ),
                blocks=blocks,
            )
        except Exception as e:
            raise RuntimeError(f"E0203: Markdown 텍스트 추출 실패 — {e}") from e

    def supports(self, mime_type: str) -> bool:
        return mime_type == self.MIME_TYPE

    # ──────────────────────────────────────────
    # Private
    # ──────────────────────────────────────────

    def _read_file(self, file_path: str) -> str:
        """파일 읽기 (UTF-8 우선, CP949 폴백)."""
        for encoding in ["utf-8", "utf-8-sig", "cp949"]:
            try:
                with open(file_path, encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        raise RuntimeError("E0202: Markdown 파일 인코딩 감지 실패")

    def _parse_tokens(self, text: str) -> list[ContentBlock]:
        """markdown-it 토큰 → ContentBlock 목록 변환."""
        tokens = self._md.parse(text)
        blocks: list[ContentBlock] = []
        block_index = 0
        page_num = 1
        i = 0

        while i < len(tokens):
            token = tokens[i]

            # heading
            if token.type == "heading_open":
                inline = tokens[i + 1] if i + 1 < len(tokens) else None
                content = inline.content if inline else ""
                if content:
                    blocks.append(ContentBlock(
                        block_id=uuid4(),
                        block_type="heading",
                        content=content.strip(),
                        page=page_num,
                        source_ref=SourceRef(page=page_num, block_index=block_index),
                    ))
                    block_index += 1
                i += 3  # heading_open + inline + heading_close
                continue

            # paragraph
            if token.type == "inline" and i > 0 and tokens[i - 1].type == "paragraph_open":
                content = token.content.strip()
                if content:
                    blocks.append(ContentBlock(
                        block_id=uuid4(),
                        block_type="text",
                        content=content,
                        page=page_num,
                        source_ref=SourceRef(page=page_num, block_index=block_index),
                    ))
                    block_index += 1

            # code block
            if token.type in ("fence", "code_block"):
                content = token.content.strip()
                if content:
                    blocks.append(ContentBlock(
                        block_id=uuid4(),
                        block_type="code",
                        content=content,
                        page=page_num,
                        source_ref=SourceRef(page=page_num, block_index=block_index),
                    ))
                    block_index += 1

            # table
            if token.type == "table_open":
                rows = []
                while i < len(tokens) and tokens[i].type != "table_close":
                    if tokens[i].type == "tr_open":
                        cells = []
                        i += 1
                        while i < len(tokens) and tokens[i].type != "tr_close":
                            if tokens[i].type == "inline":
                                cells.append(tokens[i].content.strip())
                            i += 1
                        if cells:
                            rows.append(cells)
                    i += 1
                if rows:
                    blocks.append(ContentBlock(
                        block_id=uuid4(),
                        block_type="table",
                        content=None,
                        page=page_num,
                        table=rows,
                        source_ref=SourceRef(page=page_num, block_index=block_index),
                    ))
                    block_index += 1

            i += 1

        return blocks
