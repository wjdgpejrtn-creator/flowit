"""
REQ-006 doc_parser — domain/services/pii_masking_service.py

PII 마스킹 서비스
마스킹 순서: 정규화 이후, 청킹 이전
MVP: 단방향 마스킹만 지원 (원복 불가)
"""
from __future__ import annotations

import re
from typing import Optional

from common_schemas.document import ContentBlock, DocumentBlock

from doc_parser.domain.entities.warning import WarningInfo


class PIIMaskingService:
    """PII(개인식별정보) 마스킹 서비스.

    지원 마스킹 항목:
        rrn     — 주민등록번호  예) 123456-1234567 → [MASKED_RRN]
        phone   — 전화번호      예) 010-1234-5678  → [MASKED_PHONE]
        email   — 이메일        예) abc@test.com   → [MASKED_EMAIL]
        account — 계좌번호      예) 123-456-78901  → [MASKED_ACCOUNT]
        card    — 카드번호      예) 1234-5678-9012-3456 → [MASKED_CARD]

    주의:
        하네스 도면·부품 리스트의 엔지니어링 일련번호가
        PII 패턴과 유사한 경우 오검출 가능.
        Allow-list 패턴은 별도 협의 필요. (미확정)
    """

    PATTERNS: dict[str, tuple[str, str]] = {
        "rrn":     (r"\d{6}-[1-4]\d{6}",                    "[MASKED_RRN]"),
        "phone":   (r"0\d{1,2}-\d{3,4}-\d{4}",              "[MASKED_PHONE]"),
        "email":   (r"[\w.]+@[\w.]+",                        "[MASKED_EMAIL]"),
        "account": (r"\d{3,4}-\d{2,6}-\d{5,7}",             "[MASKED_ACCOUNT]"),
        "card":    (r"\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}", "[MASKED_CARD]"),
    }

    # TODO: 하네스 엔지니어링 일련번호 오검출 방지 패턴 — 황대원님 협의 후 추가
    ALLOW_LIST: list[str] = []

    def mask_text(self, text: str) -> tuple[str, list[WarningInfo]]:
        """텍스트에서 PII 패턴을 탐지하고 마스킹.

        Args:
            text: 마스킹할 원본 텍스트

        Returns:
            tuple:
                - masked_text: 마스킹된 텍스트
                - warnings: 마스킹 발생 경고 목록
        """
        if not text:
            return text, []

        masked = text
        warnings: list[WarningInfo] = []

        for pii_type, (pattern, replacement) in self.PATTERNS.items():
            matches = re.findall(pattern, masked)
            if not matches:
                continue

            # allow-list 체크 후 마스킹
            filtered = [m for m in matches if not self.is_allow_listed(m)]
            if not filtered:
                continue

            masked = re.sub(pattern, replacement, masked)
            warnings.append(
                WarningInfo(
                    code="W0101",
                    message=f"PII 마스킹 적용: {pii_type} {len(filtered)}건",
                    detail={"pii_type": pii_type, "count": len(filtered)},
                )
            )

        return masked, warnings

    def mask_block(
        self,
        block: ContentBlock,
    ) -> tuple[ContentBlock, list[WarningInfo]]:
        """ContentBlock 단위 PII 마스킹.

        Args:
            block: 마스킹할 ContentBlock

        Returns:
            tuple:
                - masked_block: 마스킹된 ContentBlock (새 객체)
                - warnings: 마스킹 발생 경고 목록
        """
        if not block.content:
            return block, []

        masked_text, warnings = self.mask_text(block.content)

        if not warnings:
            return block, []

        # frozen=True 이므로 model_copy 로 새 객체 생성
        masked_block = block.model_copy(update={"content": masked_text})
        return masked_block, warnings

    def mask_document(
        self,
        doc: DocumentBlock,
    ) -> tuple[DocumentBlock, list[WarningInfo]]:
        """DocumentBlock 전체 PII 마스킹.

        모든 ContentBlock에 mask_block() 적용.
        PII 마스킹 이후의 데이터만 저장 (원본 민감정보 저장 금지).

        Args:
            doc: 마스킹할 DocumentBlock

        Returns:
            tuple:
                - masked_doc: 마스킹된 DocumentBlock (새 객체)
                - warnings: 전체 마스킹 경고 목록
        """
        all_warnings: list[WarningInfo] = []
        masked_blocks: list[ContentBlock] = []

        for block in doc.blocks:
            masked_block, warnings = self.mask_block(block)
            masked_blocks.append(masked_block)
            all_warnings.extend(warnings)

        if not all_warnings:
            return doc, []

        masked_doc = doc.model_copy(update={"blocks": masked_blocks})
        return masked_doc, all_warnings

    def is_allow_listed(self, text: str) -> bool:
        """Allow-list 패턴에 해당하는지 확인.

        하네스 엔지니어링 일련번호 등 오검출 방지용.
        TODO: 황대원님 협의 후 ALLOW_LIST 패턴 추가

        Args:
            text: 확인할 텍스트

        Returns:
            bool: Allow-list 해당 여부
        """
        return any(re.fullmatch(pattern, text) for pattern in self.ALLOW_LIST)