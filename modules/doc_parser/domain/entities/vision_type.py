"""
REQ-006 doc_parser — domain/entities/vision_type.py

VisionType
비전 모드 감지 유형 + 프롬프트 전략

포맷별 찰칵📸 상황에 따라 Gemma4에 넘길 프롬프트를 결정한다.
"""
from __future__ import annotations

from enum import Enum


class VisionType(str, Enum):
    """비전 추출 유형.

    TableDetector가 감지한 상황에 따라 적절한 프롬프트를 선택한다.

    Attributes:
        TABLE:      표 구조 감지 (block_type="table")
        GRAPH:      그래프/차트 이미지 감지 (block_type="image")
        CHART:      XLSX 차트 객체 감지
        CORRUPTED:  깨진 텍스트 감지 (broken_char_ratio 초과)
    """

    TABLE     = "table"
    GRAPH     = "graph"
    CHART     = "chart"
    CORRUPTED = "corrupted"

    def to_block_type(self) -> str:
        """VisionType → ContentBlock.block_type 변환."""
        mapping = {
            VisionType.TABLE:     "table",
            VisionType.GRAPH:     "image",
            VisionType.CHART:     "image",
            VisionType.CORRUPTED: "text",
        }
        return mapping[self]
