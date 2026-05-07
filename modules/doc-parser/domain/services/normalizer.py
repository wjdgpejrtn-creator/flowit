"""
REQ-006 doc-parser — domain/services/normalizer.py

기본 정규화 서비스
처리 순서: 파싱 직후, PII 마스킹 이전

v2.3: 6개 메서드 추가 (실제 문서 테스트 결과 반영 — 상세 목록 미확정)
v2.4: normalize_document() / normalize_block() 추가
"""
from __future__ import annotations

import re
import unicodedata

from common_schemas.document import ContentBlock, DocumentBlock


class Normalizer:
    """기본 정규화 서비스.

    파싱 직후, PII 마스킹 이전에 수행.
    HWP/HWPX 전처리: preprocess_hwp_text() 적용.

    처리 항목:
        - 유니코드 정규화 (NFC)
        - 연속 공백·줄바꿈 정리
        - 제어 문자 제거
        - HWP/HWPX 특수 문자 전처리
        - 앞뒤 공백 제거
    """

    # ──────────────────────────────────────────
    # Public
    # ──────────────────────────────────────────

    def normalize_document(self, doc: DocumentBlock) -> DocumentBlock:
        """DocumentBlock 전체 정규화.

        모든 ContentBlock 에 normalize_block() 적용.

        Args:
            doc: 파싱된 DocumentBlock

        Returns:
            DocumentBlock: 정규화된 DocumentBlock (새 객체)
        """
        normalized_blocks = [self.normalize_block(b) for b in doc.blocks]

        if normalized_blocks == list(doc.blocks):
            return doc

        return doc.model_copy(update={"blocks": normalized_blocks})

    def normalize_block(self, block: ContentBlock) -> ContentBlock:
        """ContentBlock 단위 정규화.

        block_type 이 "table" 인 경우 셀 단위로 정규화.

        Args:
            block: 정규화할 ContentBlock

        Returns:
            ContentBlock: 정규화된 ContentBlock (새 객체)
        """
        updates: dict = {}

        if block.content:
            normalized = self._normalize_text(block.content)
            # HWP/HWPX 전처리 추가 적용
            if block.source_ref and block.source_ref.page is not None:
                normalized = self.preprocess_hwp_text(normalized)
            if normalized != block.content:
                updates["content"] = normalized

        if block.table:
            normalized_table = self._normalize_table(block.table)
            if normalized_table != block.table:
                updates["table"] = normalized_table

        if not updates:
            return block

        return block.model_copy(update=updates)

    def preprocess_hwp_text(self, text: str) -> str:
        """HWP/HWPX 특수 문자 전처리.

        HWP 파서(pyhwp/hwp5txt)가 출력하는 특수 문자를
        표준 텍스트로 변환.

        처리 항목:
            - HWP 특수 공백 문자 → 일반 공백
            - HWP 줄바꿈 코드 → 줄바꿈
            - 한글 완성형 깨진 문자 → 제거
            - 연속 특수문자 정리

        Args:
            text: HWP 파서 출력 텍스트

        Returns:
            str: 전처리된 텍스트
        """
        if not text:
            return text

        # HWP 특수 공백 → 일반 공백
        text = re.sub(r"[\u00a0\u3000\u2002\u2003\u2009]", " ", text)

        # HWP 줄바꿈 코드 → 줄바꿈
        text = re.sub(r"\r\n|\r", "\n", text)

        # HWP 특수 구분자 제거
        text = re.sub(r"[\x0b\x0c]", "\n", text)

        # 연속 줄바꿈 3개 이상 → 2개로
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    # ──────────────────────────────────────────
    # Private
    # ──────────────────────────────────────────

    def _normalize_text(self, text: str) -> str:
        """텍스트 기본 정규화.

        처리 순서:
            1. 유니코드 NFC 정규화
            2. 제어 문자 제거
            3. 연속 공백 → 단일 공백
            4. 연속 줄바꿈 3개 이상 → 2개
            5. 앞뒤 공백 제거
        """
        if not text:
            return text

        # 1. 유니코드 NFC 정규화
        text = unicodedata.normalize("NFC", text)

        # 2. 제어 문자 제거 (줄바꿈·탭 제외)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

        # 3. 연속 공백 → 단일 공백 (줄바꿈 제외)
        text = re.sub(r"[^\S\n]+", " ", text)

        # 4. 연속 줄바꿈 3개 이상 → 2개
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 5. 앞뒤 공백 제거
        return text.strip()

    def _normalize_table(self, table: list[list]) -> list[list]:
        """표 데이터 정규화.

        각 셀에 _normalize_text() 적용.
        None 셀은 빈 문자열로 변환.
        """
        return [
            [
                self._normalize_text(str(cell)) if cell is not None else ""
                for cell in row
            ]
            for row in table
        ]

    # ──────────────────────────────────────────
    # TODO: v2.3 나머지 3개 메서드 (미확정)
    # 실제 문서 테스트 결과 반영 예정 — 조장님 확인 후 추가
    # ──────────────────────────────────────────