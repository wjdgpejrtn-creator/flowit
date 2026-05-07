"""
REQ-006 doc-parser — domain/__init__.py

domain 레이어 전체 public export

사용 예시:
    from doc_parser.domain import (
        Chunk, ChunkingStrategy,
        WarningInfo, ElapsedDetail,
        QualityMetrics, QualityGateResult, QualityConfig,
        PIIMaskRule,
        ParserPort, DocumentRepositoryPort, ConfigLoaderPort,
        NormalizationService, ChunkingService, QualityGate,
        PIIMaskingService, ParserFactory,
    )
"""
from doc_parser.domain.entities.chunk import Chunk, ChunkingStrategy
from doc_parser.domain.entities.pii import PIIMaskRule
from doc_parser.domain.entities.quality import QualityConfig, QualityGateResult, QualityMetrics
from doc_parser.domain.entities.warning import ElapsedDetail, WarningInfo
from doc_parser.domain.ports.config_port import ConfigLoaderPort
from doc_parser.domain.ports.parser_port import ParserPort
from doc_parser.domain.ports.repository_port import DocumentRepositoryPort
from doc_parser.domain.services.chunking_service import ChunkingService
from doc_parser.domain.services.normalizer import NormalizationService
from doc_parser.domain.services.parser_factory import ParserFactory
from doc_parser.domain.services.pii_masking_service import PIIMaskingService
from doc_parser.domain.services.quality_gate import QualityGate

__all__ = [
    # entities/warning.py
    "WarningInfo",
    "ElapsedDetail",
    # entities/chunk.py
    "Chunk",
    "ChunkingStrategy",
    # entities/quality.py
    "QualityMetrics",
    "QualityGateResult",
    "QualityConfig",
    # entities/pii.py
    "PIIMaskRule",
    # ports/parser_port.py
    "ParserPort",
    # ports/repository_port.py
    "DocumentRepositoryPort",
    # ports/config_port.py
    "ConfigLoaderPort",
    # services/normalizer.py
    "NormalizationService",
    # services/pii_masking_service.py
    "PIIMaskingService",
    # services/chunking_service.py
    "ChunkingService",
    # services/quality_gate.py
    "QualityGate",
    # services/parser_factory.py
    "ParserFactory",
]