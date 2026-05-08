"""
REQ-006 doc-parser — adapters/parsers/csv_parser.py

CsvParser
stdlib csv 기반 CSV 파서

처리 항목:
    - 인코딩 자동 감지 (UTF-8 → CP949 → EUC-KR 순 시도)
    - 단일 테이블 블록으로 변환
    - 빈 행 제외
"""
from __future__ import annotations

import csv
import io
from uuid import uuid4

from common_schemas.document import (
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
    SourceRef,
)

from doc_parser.domain.ports.parser_port import ParserPort

# 인코딩 시도 순서
_ENCODINGS = ["utf-8", "cp949", "euc-kr", "utf-8-sig"]


class CsvParser(ParserPort):
    """CSV 파서 구현체.

    지원 MIME 타입:
        text/csv

    Raises:
        RuntimeError: 파일 손상 또는 읽기 실패 E0202
        RuntimeError: 텍스트 추출 실패 E0203
    """

    MIME_TYPE = "text/csv"

    def parse(
        self,
        file_path: str,
        file_meta: FileMeta,
    ) -> DocumentBlock:
        """CSV 파싱 → DocumentBlock 반환.

        Args:
            file_path: CSV 파일 경로
            file_meta: 파일 메타데이터

        Returns:
            DocumentBlock: 파싱된 문서 블록 (단일 table 블록)

        Raises:
            RuntimeError: 파일 손상 (E0202), 텍스트 추출 실패 (E0203)
        """
        rows = self._read_csv(file_path)

        try:
            blocks: list[ContentBlock] = []
            if rows:
                blocks.append(
                    ContentBlock(
                        block_id=uuid4(),
                        block_type="table",
                        content=None,
                        page=1,
                        table=rows,
                        source_ref=SourceRef(
                            page=1,
                            block_index=0,
                        ),
                    )
                )

            return DocumentBlock(
                document_id=uuid4(),
                file_meta=file_meta,
                parser=ParserMeta(
                    parser_name="CsvParser",
                    parser_version="1.0.0",
                ),
                blocks=blocks,
            )

        except Exception as e:
            raise RuntimeError(f"E0203: CSV 텍스트 추출 실패 — {e}") from e

    def supports(self, mime_type: str) -> bool:
        return mime_type == self.MIME_TYPE

    # ──────────────────────────────────────────
    # Private
    # ──────────────────────────────────────────

    def _read_csv(self, file_path: str) -> list[list[str]]:
        """인코딩 자동 감지하여 CSV 읽기.

        UTF-8 → CP949 → EUC-KR → UTF-8-SIG 순으로 시도.
        빈 행 제외.

        Raises:
            RuntimeError: 모든 인코딩 실패 시 E0202
        """
        last_error: Exception | None = None

        for encoding in _ENCODINGS:
            try:
                with open(file_path, encoding=encoding, newline="") as f:
                    reader = csv.reader(f)
                    rows = [
                        row for row in reader
                        if any(cell.strip() for cell in row)
                    ]
                return rows
            except (UnicodeDecodeError, Exception) as e:
                last_error = e
                continue

        raise RuntimeError(
            f"E0202: CSV 파일 읽기 실패 — "
            f"지원 인코딩({', '.join(_ENCODINGS)}) 모두 실패: {last_error}"
        )