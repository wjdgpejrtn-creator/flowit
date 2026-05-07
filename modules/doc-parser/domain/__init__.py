"""
REQ-006 doc-parser — domain/__init__.py

domain 레이어 전체 public export

사용 예시:
    from doc_parser.domain import (
        Chunk, ChunkOverlapMeta,
        WarningInfo, ElapsedDetail,
        QualityMetrics, QualityGateResult,
        ParserPort,
        ChunkingService, QualityGate, PIIMaskingService,
    )
"""
from doc_parser.domain.entities.chunk import Chunk, ChunkOverlapMeta
from doc_parser.domain.entities.warning import ElapsedDetail, WarningInfo
from doc_parser.domain.ports.parser_port import ParserPort
from doc_parser.domain.services.chunking_service import ChunkingService
from doc_parser.domain.services.pii_masking_service import PIIMaskingService
from doc_parser.domain.services.quality_gate import QualityGate
from doc_parser.domain.value_objects.quality import QualityGateResult, QualityMetrics

__all__ = [
    # entities/warning.py
    "WarningInfo",
    "ElapsedDetail",
    # entities/chunk.py
    "ChunkOverlapMeta",
    "Chunk",
    # value_objects/quality.py
    "QualityMetrics",
    "QualityGateResult",
    # ports/parser_port.py
    "ParserPort",
    # services/pii_masking_service.py
    "PIIMaskingService",
    # services/chunking_service.py
    "ChunkingService",
    # services/quality_gate.py
    "QualityGate",
]