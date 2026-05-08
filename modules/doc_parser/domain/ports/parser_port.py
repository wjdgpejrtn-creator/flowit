"""
REQ-006 doc_parser — domain/ports/parser_port.py

파서 구현체가 반드시 따라야 할 ABC 계약
구현체 위치: doc_parser/adapters/parsers/
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from common_schemas.document import DocumentBlock, FileMeta


class ParserPort(ABC):
    """파서 Port (인터페이스 계약).

    Clean Architecture DIP 원칙:
        - 안쪽(domain)이 인터페이스를 정의
        - 바깥쪽(adapters)이 구현체를 제공
        - domain은 구현체를 직접 알지 못함

    구현체 목록 (adapters/parsers/):
        PdfParser   — .pdf
        DocxParser  — .docx
        XlsxParser  — .xlsx
        CsvParser   — .csv
        PptxParser  — .pptx
        HwpParser   — .hwp
        HwpxParser  — .hwpx
    """

    @abstractmethod
    def parse(
        self,
        file_path: str,
        file_meta: FileMeta,
    ) -> DocumentBlock:
        """문서를 파싱하여 DocumentBlock 반환.

        Args:
            file_path: 파싱할 파일 경로
            file_meta: 파일 메타데이터 (mime_type, file_size 등)

        Returns:
            DocumentBlock: 파싱된 문서 블록

        Raises:
            E0201: 지원하지 않는 파일 형식
            E0202: 파일 손상 또는 읽기 실패
            E0203: 텍스트 추출 실패
            E0212: 스캔 PDF 감지 (OCR 필요)
        """
        ...

    @abstractmethod
    def supports(self, mime_type: str) -> bool:
        """이 파서가 해당 MIME 타입을 지원하는지 여부.

        Args:
            mime_type: 확인할 MIME 타입
                예) "application/pdf"
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        Returns:
            bool: 지원 여부
        """
        ...