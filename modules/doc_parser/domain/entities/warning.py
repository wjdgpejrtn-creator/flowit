"""
REQ-006 doc_parser — domain/entities/warning.py

파싱 중 발생한 경고 정보 및 단계별 처리 시간 엔티티
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class WarningInfo(BaseModel):
    """파싱 중 발생한 경고 정보.

    Attributes:
        code: 에러코드 (E0201, E0202 등 README 에러코드 기준)
        message: 사용자에게 전달할 메시지
        detail: 추가 디버깅 정보 (선택)
    """

    code: str
    message: str
    detail: Optional[dict[str, Any]] = None


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