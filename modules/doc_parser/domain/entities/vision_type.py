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
        FULL_PAGE:  DOCX/HWP 전체 페이지 찰칵
        CORRUPTED:  깨진 텍스트 감지 (broken_char_ratio 초과)
    """

    TABLE     = "table"
    GRAPH     = "graph"
    CHART     = "chart"
    FULL_PAGE = "full_page"
    CORRUPTED = "corrupted"

    def to_block_type(self) -> str:
        """VisionType → ContentBlock.block_type 변환."""
        mapping = {
            VisionType.TABLE:     "table",
            VisionType.GRAPH:     "image",
            VisionType.CHART:     "image",
            VisionType.FULL_PAGE: "text",
            VisionType.CORRUPTED: "text",
        }
        return mapping[self]


class VisionPromptStrategy:
    """VisionType별 Gemma4 프롬프트 전략.

    모든 프롬프트는 한국어 문서 대응을 기본으로 한다.
    """

    _PROMPTS: dict[VisionType, str] = {
        VisionType.TABLE: (
            "이 이미지에 있는 표의 헤더와 모든 행 데이터를 빠짐없이 텍스트로 추출해줘. "
            "표 구조를 마크다운 표 형식으로 출력해줘."
        ),
        VisionType.GRAPH: (
            "이 이미지에 있는 그래프의 제목, 축 라벨, 범례, 데이터 추세를 설명해줘. "
            "수치가 보이면 포함해줘."
        ),
        VisionType.CHART: (
            "이 차트의 제목, 축, 범례, 주요 데이터 포인트와 전체적인 추세를 설명해줘. "
            "수치가 보이면 포함해줘."
        ),
        VisionType.FULL_PAGE: (
            "이 페이지에 있는 모든 텍스트, 표, 그래프 내용을 위에서 아래 순서대로 빠짐없이 추출해줘. "
            "표가 있으면 마크다운 표 형식으로, 그래프가 있으면 내용을 설명해줘."
        ),
        VisionType.CORRUPTED: (
            "이 페이지에서 읽을 수 있는 모든 텍스트를 추출해줘. "
            "깨진 글자는 건너뛰고 읽을 수 있는 내용만 추출해줘."
        ),
    }

    @classmethod
    def get(cls, vision_type: VisionType) -> str:
        """VisionType에 맞는 프롬프트 반환."""
        return cls._PROMPTS[vision_type]
