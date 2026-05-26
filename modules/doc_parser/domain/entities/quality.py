"""
REQ-006 doc_parser — domain/entities/quality.py

SSOT 이관 (REQ-012, common_schemas 0.11.0): `QualityMetrics`·`ParseCoverage`·
`QualityGateResult`는 common_schemas로 이관됨 (아래 shim 재노출). `QualityConfig`는
config/parser_quality.yaml에서 로드하는 doc_parser 내부 설정 VO라 잔류한다.
신규 코드는 이관 타입을 `from common_schemas import ...`로 직접 import할 것.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from common_schemas import ParseCoverage, QualityGateResult, QualityMetrics


class QualityConfig(BaseModel):
    """품질 게이트 설정 VO.

    config/parser_quality.yaml 에서 로드.
    frozen=True → 생성 후 불변.

    Attributes:
        min_text_length: 최소 텍스트 길이 (절대값)
        min_text_per_page: 페이지당 최소 텍스트 길이
        korean_ratio_warn: 한글 비율 경고 임계값
        broken_char_warn: 깨진 문자 비율 경고 임계값
        blocks_per_page_warn: 페이지당 블록 수 경고 임계값
        max_parser_warnings: 최대 허용 경고 수
        min_heading_ratio: 최소 heading 비율
        min_valid_table_ratio: 최소 유효 표 비율
        min_structural_chunk_ratio: 최소 구조적 청크 비율
        warn_threshold_count: warning → manual_correction_required 격상 기준
    """

    model_config = ConfigDict(frozen=True)

    min_text_length: int
    min_text_per_page: int
    korean_ratio_warn: float
    broken_char_warn: float
    blocks_per_page_warn: float
    max_parser_warnings: int
    min_heading_ratio: float
    min_valid_table_ratio: float
    min_structural_chunk_ratio: float
    warn_threshold_count: int


__all__ = ["QualityMetrics", "ParseCoverage", "QualityGateResult", "QualityConfig"]
