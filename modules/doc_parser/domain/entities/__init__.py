"""
REQ-006 doc_parser — domain/entities/__init__.py

domain/entities 레이어 public export
"""
from doc_parser.domain.entities.chunk import Chunk, ChunkingStrategy
from doc_parser.domain.entities.pii import PIIMaskRule
from doc_parser.domain.entities.quality import QualityConfig, QualityGateResult, QualityMetrics
from doc_parser.domain.entities.vision_type import VisionPromptStrategy, VisionType
from doc_parser.domain.entities.warning import ElapsedDetail, WarningInfo

__all__ = [
    # warning.py
    "WarningInfo",
    "ElapsedDetail",
    # chunk.py
    "Chunk",
    "ChunkingStrategy",
    # quality.py
    "QualityMetrics",
    "QualityGateResult",
    "QualityConfig",
    # pii.py
    "PIIMaskRule",
    # vision_type.py
    "VisionType",
    "VisionPromptStrategy",
]
