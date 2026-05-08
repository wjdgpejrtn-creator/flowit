"""
REQ-006 doc_parser — domain/entities/pii.py

PII 마스킹 규칙 정의 엔티티
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PIIMaskRule(BaseModel):
    """PII 마스킹 규칙 정의.

    config/parser_quality.yaml 에서 로드.
    frozen=True → 생성 후 불변.

    Attributes:
        pattern: 정규식 패턴
        replacement: 마스킹 대체 문자열 (예: [MASKED_RRN])
        label: 마스킹 항목명 (예: rrn, phone, email)
    """

    model_config = ConfigDict(frozen=True)

    pattern: str
    replacement: str
    label: str

    @classmethod
    def defaults(cls) -> list["PIIMaskRule"]:
        """기본 PII 마스킹 규칙 목록 반환.

        README 기준 5종:
            rrn, phone, email, account, card
        """
        return [
            cls(pattern=r"\d{6}-[1-4]\d{6}",                    replacement="[MASKED_RRN]",     label="rrn"),
            cls(pattern=r"0\d{1,2}-\d{3,4}-\d{4}",              replacement="[MASKED_PHONE]",   label="phone"),
            cls(pattern=r"[\w.]+@[\w.]+",                        replacement="[MASKED_EMAIL]",   label="email"),
            cls(pattern=r"\d{3,4}-\d{2,6}-\d{5,7}",             replacement="[MASKED_ACCOUNT]", label="account"),
            cls(pattern=r"\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}", replacement="[MASKED_CARD]",    label="card"),
        ]