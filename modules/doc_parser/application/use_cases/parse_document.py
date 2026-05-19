"""
REQ-006 doc_parser — application/use_cases/parse_document.py

ParseDocumentUseCase
파일 경로 + FileMeta → DocumentBlock + QualityGateResult

처리 흐름:
    파일 입력
      → ParserFactory 로 파서 선택 (mime_type 기준)
      → parse() → DocumentBlock
      → NormalizationService.normalize_document()
      → PIIMaskingService.mask_document()
      → QualityGate.evaluate()
      → DocumentBlock + QualityGateResult 반환
"""
from __future__ import annotations

from common_schemas.document import DocumentBlock, FileMeta

from doc_parser.domain.ports.parser_port import ParserPort
from doc_parser.domain.services.normalization import NormalizationService
from doc_parser.domain.services.pii_masking import PIIMaskingService
from doc_parser.domain.services.quality_gate import QualityGate
from doc_parser.domain.entities.quality import QualityGateResult


class ParseDocumentUseCase:
    """문서 파싱 유스케이스.

    적절한 파서 선택 → 파싱 → 정규화 → PII 마스킹 → 품질 검증.

    Clean Architecture DIP 원칙:
        - ParserPort(ABC) 만 알고 구체 구현체(PdfParser 등)는 모름
        - 파서 목록은 외부(Composition Root)에서 주입

    Args:
        parsers: ParserPort 구현체 목록 (DI로 주입)
            예) [PdfParser(), DocxParser(), XlsxParser(), ...]
        normalizer: NormalizationService 인스턴스
        pii_masking_service: PIIMaskingService 인스턴스
        quality_gate: QualityGate 인스턴스
    """

    def __init__(
        self,
        parsers: list[ParserPort],
        normalizer: NormalizationService,
        pii_masking_service: PIIMaskingService,
        quality_gate: QualityGate,
    ) -> None:
        self._parsers = parsers
        self._normalizer = normalizer
        self._pii = pii_masking_service
        self._quality_gate = quality_gate

    def execute(
        self,
        file_path: str,
        file_meta: FileMeta,
    ) -> tuple[DocumentBlock, QualityGateResult]:
        """문서 파싱 실행.

        Args:
            file_path: 파싱할 파일 경로
            file_meta: 파일 메타데이터 (mime_type, file_size 등)

        Returns:
            tuple:
                - DocumentBlock: 정규화 + PII 마스킹된 파싱 결과
                - QualityGateResult: 품질 판정 결과

        Raises:
            ValueError: 지원하지 않는 MIME 타입 (E0201)
        """
        # ── 1. 파서 선택 ──
        parser = self._get_parser(file_meta.mime_type)

        # ── 2. 파싱 ──
        document = parser.parse(file_path, file_meta)

        # ── 3. 정규화 (파싱 직후, PII 마스킹 이전) ──
        normalized_document = self._normalizer.normalize_document(document)

        # ── 4. PII 마스킹 (정규화 이후, 청킹 이전) ──
        masked_document, _pii_warnings = self._pii.mask_document(normalized_document)

        # ── 5. 품질 검증 (청크 없이 문서 레벨만 먼저 판정) ──
        quality_result = self._quality_gate.evaluate(masked_document, chunks=[])

        return masked_document, quality_result

    def _get_parser(self, mime_type: str) -> ParserPort:
        """MIME 타입에 맞는 파서 반환.

        Args:
            mime_type: 파일 MIME 타입

        Returns:
            ParserPort: 해당 MIME 타입을 지원하는 파서

        Raises:
            ValueError: 지원하지 않는 MIME 타입 (E0201)
        """
        for parser in self._parsers:
            if parser.supports(mime_type):
                return parser
        raise ValueError(f"E0201: 지원하지 않는 파일 형식 — {mime_type}")