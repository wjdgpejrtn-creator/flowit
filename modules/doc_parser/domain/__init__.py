"""
REQ-006 doc_parser — domain/__init__.py

domain 레이어 전체 public export

사용 예시:
    from doc_parser.domain import (
        Chunk, ChunkingStrategy,
        WarningInfo, ElapsedDetail,
        QualityMetrics, QualityGateResult, QualityConfig,
        PIIMaskRule,
        ParserPort, ConfigLoaderPort, VisionPort,
        NormalizationService, ChunkingService, QualityGate,
        PIIMaskingService,
        VisionType,
    )
"""
from doc_parser.domain.entities.chunk import Chunk, ChunkingStrategy
from doc_parser.domain.entities.pii import PIIMaskRule
from doc_parser.domain.entities.quality import QualityConfig, QualityGateResult, QualityMetrics
from doc_parser.domain.entities.vision_type import VisionType
from doc_parser.domain.entities.warning import ElapsedDetail, WarningInfo
from doc_parser.domain.ports.config_port import ConfigLoaderPort
from doc_parser.domain.ports.parser_port import ParserPort
from doc_parser.domain.ports.vision_port import VisionPort
from doc_parser.domain.services.chunking_service import ChunkingService
from doc_parser.domain.services.normalization import NormalizationService
from doc_parser.domain.services.pii_masking import PIIMaskingService
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
    # entities/vision_type.py
    "VisionType",
    # VisionPromptStrategy → adapters/vision/prompts.py로 이동
    # ports/parser_port.py
    "ParserPort",
    # ports/config_port.py
    "ConfigLoaderPort",
    # ports/vision_port.py
    "VisionPort",
    # services/normalization.py
    "NormalizationService",
    # services/pii_masking.py
    "PIIMaskingService",
    # services/chunking_service.py
    "ChunkingService",
    # services/quality_gate.py
    "QualityGate",
]
