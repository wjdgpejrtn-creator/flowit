"""
REQ-006 doc_parser — adapters/parsers/hwp_parser.py

HwpParser
pyhwp(hwp5txt) 기반 HWP 파서

제한 사항 (MVP):
    - 표·서식·각주 완전 복원 불가
    - 복잡 표·이미지 내 텍스트 제외
    - 파싱 실패 시 E0205 반환
"""
from __future__ import annotations

import re
import subprocess
from uuid import uuid4

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

    pyhwp(hwp5txt) 를 subprocess 로 실행하여 텍스트 추출.

    지원 MIME 타입:
        application/x-hwp

    제한 지원:
        표·서식·각주 완전 복원 불가 (Phase 2)

    Raises:
        RuntimeError: HWP 파서 제한 지원 실패 E0205
        RuntimeError: 파일 손상 또는 읽기 실패 E0202
    """

    MIME_TYPE = "application/x-hwp"

    def parse(self, file_path: str, file_meta: FileMeta) -> DocumentBlock:
        text = self._extract_text(file_path)
        try:
            blocks = self._text_to_blocks(text)
            return DocumentBlock(
                document_id=uuid4(),
                file_meta=file_meta,
                parser=ParserMeta(parser_name="HwpParser", parser_version="1.0.0"),
                blocks=blocks,
            )
        except Exception as e:
            raise RuntimeError(f"E0205: HWP 파서 제한 지원 실패 — {e}") from e

    def supports(self, mime_type: str) -> bool:
        return mime_type == self.MIME_TYPE

    def _extract_text(self, file_path: str) -> str:
        try:
            result = subprocess.run(
                ["hwp5txt", file_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"E0205: HWP 파서 제한 지원 실패 — {result.stderr}")
            return result.stdout
        except FileNotFoundError:
            raise RuntimeError(
                "E0205: HWP 파서 제한 지원 실패 — hwp5txt 미설치. pip install pyhwp 실행 후 재시도"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("E0202: HWP 파일 읽기 실패 — 파싱 타임아웃")
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
            para = para.strip()
            if not para:
                continue
            blocks.append(ContentBlock(
                block_id=uuid4(),
                block_type=self._detect_block_type(para),
                content=para,
                page=page_num,
                source_ref=SourceRef(page=page_num, block_index=block_index),
            ))
            block_index += 1
        return blocks

    def _detect_block_type(self, text: str) -> str:
        text = text.strip()
        is_short = len(text) <= 50
        no_newline = "\n" not in text
        numbered = bool(re.match(r"^(\d+[\.\)]|제\s*\d+\s*[조항절장]|[가-힣]\.|[IVX]+\.)\s", text))
        if is_short and no_newline and numbered:
            return "heading"
        if is_short and no_newline and text.endswith(("장", "절", "항", "조")):
            return "heading"
        return "text"