"""
REQ-006 doc_parser — adapters/vision/prompts.py

VisionPromptStrategy
VisionType별 Gemma4 프롬프트 정책

프롬프트는 정책 변경이 잦은 객체이므로 domain이 아닌 adapters에 위치한다.
한국어 문서 대응을 기본으로 한다.
"""
from __future__ import annotations

from doc_parser.domain.entities.vision_type import VisionType


class VisionPromptStrategy:
    """VisionType별 Gemma4 프롬프트 전략."""

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
        VisionType.CORRUPTED: (
            "이 페이지에서 읽을 수 있는 모든 텍스트를 추출해줘. "
            "깨진 글자는 건너뛰고 읽을 수 있는 내용만 추출해줘."
        ),
    }

    @classmethod
    def get(cls, vision_type: VisionType) -> str:
        """VisionType에 맞는 프롬프트 반환."""
        return cls._PROMPTS[vision_type]
