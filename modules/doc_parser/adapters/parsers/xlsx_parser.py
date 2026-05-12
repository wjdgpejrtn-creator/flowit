"""
REQ-006 doc_parser — adapters/parsers/xlsx_parser.py

XlsxParser
openpyxl 기반 Excel 파서

처리 항목:
    - 시트별 테이블 블록 변환
    - SheetMeta 생성 (시트명, 행/열 수)
    - read_only=True 모드 (대용량 파일 대응)
    - styles.xml count 속성 호환성 문제 자동 복구
"""
from __future__ import annotations

import io
import re
import zipfile
from uuid import uuid4

import openpyxl

from common_schemas.document import (
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
    SheetMeta,
    SourceRef,
)

from doc_parser.domain.ports.parser_port import ParserPort


class XlsxParser(ParserPort):
    """Excel 파서 구현체.

    지원 MIME 타입:
        application/vnd.openxmlformats-officedocument.spreadsheetml.sheet

    Raises:
        RuntimeError: 파일 손상 또는 읽기 실패 E0202
        RuntimeError: 텍스트 추출 실패 E0203
    """

    MIME_TYPE = (
        "application/vnd.openxmlformats-officedocument"
        ".spreadsheetml.sheet"
    )

    # ──────────────────────────────────────────
    # ParserPort 구현
    # ──────────────────────────────────────────

    def parse(
        self,
        file_path: str,
        file_meta: FileMeta,
    ) -> DocumentBlock:
        """XLSX 파싱 → DocumentBlock 반환.

        Args:
            file_path: XLSX 파일 경로
            file_meta: 파일 메타데이터

        Returns:
            DocumentBlock: 파싱된 문서 블록 (시트별 table 블록)

        Raises:
            RuntimeError: 파일 손상 (E0202), 텍스트 추출 실패 (E0203)
        """
        try:
            wb = self._load_workbook_safe(file_path)
        except Exception as e:
            raise RuntimeError(f"E0202: XLSX 파일 읽기 실패 — {e}") from e

        try:
            blocks: list[ContentBlock] = []
            sheet_metas: list[SheetMeta] = []
            block_index = 0

            for sheet_index, sheet_name in enumerate(wb.sheetnames):
                ws = wb[sheet_name]
                rows = self._extract_rows(ws)

                if not rows:
                    continue

                row_count = len(rows)
                col_count = max(len(r) for r in rows) if rows else 0

                sheet_metas.append(
                    SheetMeta(
                        sheet_name=sheet_name,
                        row_count=row_count,
                        col_count=col_count,
                    )
                )

                blocks.append(
                    ContentBlock(
                        block_id=uuid4(),
                        block_type="table",
                        content=None,
                        page=sheet_index + 1,  # 시트 번호를 페이지로
                        table=rows,
                        source_ref=SourceRef(
                            page=sheet_index + 1,
                            sheet_name=sheet_name,
                            block_index=block_index,
                        ),
                    )
                )
                block_index += 1

            wb.close()

            # FileMeta 에 SheetMeta 반영
            updated_file_meta = file_meta.model_copy(
                update={"sheet_meta": sheet_metas}
            )

            return DocumentBlock(
                document_id=uuid4(),
                file_meta=updated_file_meta,
                parser=ParserMeta(
                    parser_name="XlsxParser",
                    parser_version="1.0.0",
                ),
                blocks=blocks,
            )

        except Exception as e:
            raise RuntimeError(f"E0203: XLSX 텍스트 추출 실패 — {e}") from e

    def supports(self, mime_type: str) -> bool:
        return mime_type == self.MIME_TYPE

    # ──────────────────────────────────────────
    # Private
    # ──────────────────────────────────────────

    def _load_workbook_safe(
        self, file_path: str
    ) -> openpyxl.Workbook:
        """XLSX 로딩 — styles.xml count 속성 호환성 문제 자동 복구.

        일부 XLSX 파일의 styles.xml에 openpyxl이 인식하지 못하는
        count 속성이 포함된 경우(CellStyle.__init__() got an unexpected
        keyword argument 'count'), 해당 속성을 제거한 뒤 재시도한다.
        데이터 셀 값에는 영향 없음.

        Args:
            file_path: XLSX 파일 경로

        Returns:
            openpyxl.Workbook

        Raises:
            Exception: 복구 후에도 로딩 실패 시 원본 예외 전파
        """
        try:
            return openpyxl.load_workbook(
                file_path, read_only=True, data_only=True
            )
        except Exception:
            # styles.xml 에서 count 속성 제거 후 재시도
            with open(file_path, "rb") as f:
                raw = f.read()

            fixed_buf = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(raw), "r") as zin:
                with zipfile.ZipFile(
                    fixed_buf, "w", zipfile.ZIP_DEFLATED
                ) as zout:
                    for item in zin.namelist():
                        if item == "xl/styles.xml":
                            xml = zin.read(item).decode("utf-8")
                            xml = re.sub(r'\s+count="\d+"', "", xml)
                            zout.writestr(item, xml)
                        else:
                            zout.writestr(item, zin.read(item))

            fixed_buf.seek(0)
            return openpyxl.load_workbook(
                fixed_buf, read_only=True, data_only=True
            )

    def _extract_rows(self, ws: openpyxl.worksheet.worksheet.Worksheet) -> list[list[str]]:
        """워크시트에서 행 데이터 추출.

        빈 행은 제외.
        셀 값은 문자열로 변환, None → 빈 문자열.
        """
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(cell) if cell is not None else "" for cell in row]
            # 전체가 빈 행은 제외
            if any(c.strip() for c in cells):
                rows.append(cells)
        return rows
