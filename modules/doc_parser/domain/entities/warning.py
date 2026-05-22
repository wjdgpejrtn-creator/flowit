"""
REQ-006 doc_parser — domain/entities/warning.py

SSOT 이관 (REQ-012, common_schemas 0.11.0): `WarningInfo`는 common_schemas로
이관됨 (아래 shim 재노출). `ElapsedDetail`은 파이프라인 단계별 처리 시간으로
doc_parser 내부 타입이라 잔류한다.
"""
from __future__ import annotations

from pydantic import BaseModel

from common_schemas import WarningInfo


class ElapsedDetail(BaseModel):
    """파이프라인 단계별 처리 시간 (밀리초).

    파이프라인 5단계:
        parse → normalize → masking → chunking → quality_gate

    Attributes:
        parse_ms: 문서 파싱 소요 시간 (ms)
        normalize_ms: 정규화 소요 시간 (ms)
        masking_ms: PII 마스킹 소요 시간 (ms)
        chunking_ms: 청킹 소요 시간 (ms)
        quality_gate_ms: 품질 게이트 소요 시간 (ms)
    """

    parse_ms: int = 0
    normalize_ms: int = 0
    masking_ms: int = 0
    chunking_ms: int = 0
    quality_gate_ms: int = 0

    @property
    def total_ms(self) -> int:
        """전체 처리 시간 합계."""
        return (
            self.parse_ms
            + self.normalize_ms
            + self.masking_ms
            + self.chunking_ms
            + self.quality_gate_ms
        )


__all__ = ["WarningInfo", "ElapsedDetail"]
