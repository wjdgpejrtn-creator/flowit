"""
REQ-006 doc_parser — domain/services/__init__.py

domain/services 레이어 public export

ParserFactory는 adapters/parser_factory.py로 이동됨.
(adapters 의존성으로 인해 domain에 둘 수 없음)
"""
from doc_parser.domain.services.chunking_service import ChunkingService
from doc_parser.domain.services.normalization import NormalizationService
from doc_parser.domain.services.pii_masking import PIIMaskingService
from doc_parser.domain.services.quality_gate import QualityGate

__all__ = [
    # normalization.py
    "NormalizationService",
    # pii_masking.py
    "PIIMaskingService",
    # chunking_service.py
    "ChunkingService",
    # quality_gate.py
    "QualityGate",
]
