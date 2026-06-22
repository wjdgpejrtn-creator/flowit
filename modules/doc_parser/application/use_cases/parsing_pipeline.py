"""
REQ-006 doc_parser — application/use_cases/parsing_pipeline.py

ParsingPipeline
전체 파이프라인 오케스트레이션

처리 흐름:
    파일 입력
      → ParserFactory 로 파서 선택
      → parse() → DocumentBlock
      → NormalizationService.normalize_document()
      → PIIMaskingService.mask_document()
      → ChunkingService.chunk()
      → QualityGate.evaluate()
      → (DocumentBlock, list[Chunk], QualityGateResult) 반환
"""
from __future__ import annotations

from common_schemas.document import DocumentBlock, FileMeta

from doc_parser.adapters.parser_factory import ParserFactory
from doc_parser.domain.entities.chunk import Chunk
from doc_parser.domain.entities.quality import QualityGateResult
from doc_parser.domain.ports.config_port import ConfigLoaderPort
from doc_parser.domain.services.chunking_service import ChunkingService
from doc_parser.domain.services.normalization import NormalizationService
from doc_parser.domain.services.pii_masking import PIIMaskingService
from doc_parser.domain.services.quality_gate import QualityGate


class ParsingPipeline:
    """전체 파싱 파이프라인 오케스트레이션.

    파서 선택 → 파싱 → 정규화 → PII 마스킹 →
    청킹 → 품질 검증 → 결과 반환.

    저장은 storage(REQ-008) DocumentRepositoryPort 담당.

    Args:
        parser_factory: ParserFactory 인스턴스
        normalization_service: NormalizationService 인스턴스
        pii_masking_service: PIIMaskingService 인스턴스
        quality_gate: QualityGate 인스턴스
        chunking_service: ChunkingService 인스턴스
        config_loader: ConfigLoaderPort 구현체 (DI로 주입)
    """

    def __init__(
        self,
        parser_factory: ParserFactory,
        normalization_service: NormalizationService,
        pii_masking_service: PIIMaskingService,
        quality_gate: QualityGate,
        chunking_service: ChunkingService,
        config_loader: ConfigLoaderPort,
    ) -> None:
        self._factory = parser_factory
        self._normalizer = normalization_service
        self._pii = pii_masking_service
        self._quality_gate = quality_gate
        self._chunking = chunking_service
        self._config_loader = config_loader

    def execute(
        self,
        file_path: str,
        file_meta: FileMeta,
    ) -> tuple[DocumentBlock, list[Chunk], QualityGateResult]:
        """전체 파싱 파이프라인 실행.

        Args:
            file_path: 파싱할 파일 경로
            file_meta: 파일 메타데이터

        Returns:
            tuple:
                - DocumentBlock: 정규화 + PII 마스킹된 파싱 결과
                - list[Chunk]: 청킹 결과
                - QualityGateResult: 품질 판정 결과

        Raises:
            ValueError: 지원하지 않는 MIME 타입 (E0201)
            RuntimeError: 파싱 실패 (E0202, E0203 등)
        """
        # ── 1. 파서 선택 ──
        parser = self._factory.get(file_meta.mime_type)

        # ── 2. 파싱 ──
        document = parser.parse(file_path, file_meta)

        # ── 3. 정규화 (파싱 직후, PII 마스킹 이전) ──
        normalized_document = self._normalizer.normalize_document(document)

        # ── 4. PII 마스킹 (정규화 이후, 청킹 이전) ──
        pii_rules = self._config_loader.load_pii_rules()
        masked_document, _pii_warnings = self._pii.mask_document(normalized_document)

        # ── 5. 청킹 ──
        strategy = self._config_loader.load_chunking_strategy()
        chunks = self._chunking.chunk(masked_document, strategy=strategy)

        # ── 6. 품질 검증 ──
        quality_config = self._config_loader.load_quality_config()
        quality_result = self._quality_gate.evaluate(masked_document, chunks, quality_config)

        return masked_document, chunks, quality_result
