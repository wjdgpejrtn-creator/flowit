"""
REQ-006 doc_parser — adapters/vision/table_detector.py

TableDetector
블록 스트림에서 비전 모드가 필요한 블록을 감지한다.

감지 원칙:
    "에엥?" 하면 찰칵📸 — 놓치는 것보다 잘못 찍는 게 낫다.

감지 케이스:
    1. block_type이 명시적으로 표/이미지/그래프인 경우 (구조적 감지)
    2. 텍스트인데 내용이 없거나 깨진 경우 (휴리스틱 감지)
"""
from __future__ import annotations

from common_schemas.document import ContentBlock

from doc_parser.domain.entities.vision_type import VisionType


class TableDetector:
    """블록 스트림 실시간 비전 트리거 감지기.

    InterleavingParser가 BaseParser 스트림을 흘리는 동안
    각 블록에 대해 detect()를 호출한다.

    Args:
        broken_char_threshold: 깨진 문자 비율 임계값 (기본 0.3)
            parser_quality.yaml의 broken_char_warn 값을 주입받는다.

    Example:
        detector = TableDetector(broken_char_threshold=0.3)
        vision_type = detector.detect(block)
        if vision_type:
            # 찰칵📸
    """

    def __init__(self, broken_char_threshold: float = 0.3) -> None:
        self._broken_char_threshold = broken_char_threshold

    def detect(self, block: ContentBlock) -> VisionType | None:
        """블록을 보고 비전 모드 필요 여부 판단.

        Args:
            block: 파서에서 흘러나온 ContentBlock

        Returns:
            VisionType: 비전 모드가 필요한 경우 유형 반환
            None: 정상 텍스트 → 그냥 쫘라라락
        """
        # ── 1. 구조적 감지 (block_type 명시) ──
        if block.block_type == "table":
            return VisionType.TABLE

        if block.block_type == "image":
            return VisionType.GRAPH

        # ── 2. 휴리스틱 감지 (텍스트인데 에엥?) ──
        if block.block_type in ("text", "heading"):

            # 텍스트가 아예 없음
            if not block.content or not block.content.strip():
                return VisionType.CORRUPTED

            # 깨진 문자 비율 초과
            if self._broken_char_ratio(block.content) > self._broken_char_threshold:
                return VisionType.CORRUPTED

        # ── 3. 정상 텍스트 ──
        return None

    # ──────────────────────────────────────────
    # Private
    # ──────────────────────────────────────────

    def _broken_char_ratio(self, text: str) -> float:
        """깨진 문자 비율 계산.

        깨진 문자 판단 기준:
            - 유니코드 대체 문자 (U+FFFD)
            - 제어 문자 (탭/줄바꿈 제외)
            - 사용 불가 유니코드 영역

        Args:
            text: 검사할 텍스트

        Returns:
            float: 0.0 ~ 1.0 (깨진 문자 비율)
        """
        if not text:
            return 0.0

        broken = sum(
            1 for ch in text
            if ch == "\ufffd"                          # 유니코드 대체 문자
            or (ord(ch) < 32 and ch not in "\t\n\r")  # 제어 문자
            or (0xFFF0 <= ord(ch) <= 0xFFFF)           # 사용 불가 영역
        )
        return broken / len(text)
