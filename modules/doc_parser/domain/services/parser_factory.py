"""
REQ-006 doc_parser — adapters/parsers/parser_factory.py

ParserFactory
MIME 타입 기준으로 적절한 파서 선택

사용 예시:
    factory = ParserFactory()
    factory.register(PdfParser())
    factory.register(DocxParser())
    parser = factory.get("application/pdf")
"""
from __future__ import annotations

from doc_parser.domain.ports.parser_port import ParserPort


class ParserFactory:
    """파서 선택 팩토리.

    ParserPort 구현체를 등록하고 MIME 타입에 맞는 파서를 반환.

    Raises:
        ValueError: 지원하지 않는 MIME 타입 (E0201)
    """

    def __init__(self) -> None:
        self._parsers: list[ParserPort] = []

    def register(self, parser: ParserPort) -> None:
        """파서 등록.

        Args:
            parser: 등록할 ParserPort 구현체
        """
        self._parsers.append(parser)

    def get(self, mime_type: str) -> ParserPort:
        """MIME 타입에 맞는 파서 반환.

        Args:
            mime_type: 파일 MIME 타입
                예) "application/pdf"
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        Returns:
            ParserPort: 해당 MIME 타입을 지원하는 파서

        Raises:
            ValueError: 지원하지 않는 MIME 타입 (E0201)
        """
        for parser in self._parsers:
            if parser.supports(mime_type):
                return parser
        raise ValueError(f"E0201: 지원하지 않는 파일 형식 — {mime_type}")

    def supports(self, mime_type: str) -> bool:
        """해당 MIME 타입을 지원하는 파서가 있는지 확인."""
        return any(p.supports(mime_type) for p in self._parsers)

    @property
    def registered_parsers(self) -> list[ParserPort]:
        """등록된 파서 목록."""
        return list(self._parsers)