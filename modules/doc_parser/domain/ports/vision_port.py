"""
REQ-006 doc_parser — domain/ports/vision_port.py

VisionPort
비전 추출기 인터페이스 (ABC)

구현체:
    adapters/vision/vision_extractor.py — fitz(PyMuPDF) + Gemma4 구현
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from common_schemas.document import ContentBlock

from doc_parser.domain.entities.vision_type import VisionType


class VisionPort(ABC):
    """비전 추출기 포트.

    파일의 특정 페이지를 이미지로 캡처하고
    Gemma4 등 비전 모델로 텍스트를 추출하는 인터페이스.

    구현체는 adapters/vision/에 위치한다.
    """

    @abstractmethod
    def extract(
        self,
        file_path: str,
        vision_type: VisionType,
        page_num: int = 1,
        block_index: int = 0,
    ) -> ContentBlock | None:
        """파일의 특정 페이지를 찰칵📸하고 텍스트 추출.

        Args:
            file_path: 원본 파일 경로
            vision_type: 비전 추출 유형 (프롬프트 결정)
            page_num: 캡처할 페이지 번호 (1-based)
            block_index: ContentBlock 순서 인덱스

        Returns:
            ContentBlock: 비전 추출 결과
            None: 캡처 또는 추출 실패 시
        """
        ...
