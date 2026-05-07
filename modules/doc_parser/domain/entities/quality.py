"""
REQ-006 doc-parser — domain/entities/quality.py

품질 게이트 결과 및 설정 엔티티
모든 임계값은 config/parser_quality.yaml 에서 읽음 — 코드 내 숫자 직접 기입 금지
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from doc_parser.domain.entities.warning import WarningInfo


class QualityMetrics(BaseModel):
    """파싱 품질 측정 지표 VO.

    QualityGate.evaluate() 가 계산하여 QualityGateResult 에 포함.
    frozen=True → 생성 후 불변 (Value Object 원칙)

    Attributes:
        korean_ratio: 한글 문자 비율 (0.0 ~ 1.0)
        broken_char_ratio: 깨진 문자 비율 (0.0 ~ 1.0)
        blocks_per_page: 페이지당 평균 블록 수
        heading_ratio: 전체 블록 중 heading 비율
        valid_table_ratio: 유효한 표 비율
        structural_chunk_ratio: 구조적 청크 비율
        total_chunks: 전체 청크 수
        avg_tokens: 청크당 평균 토큰 수
    """

    model_config = ConfigDict(frozen=True)

    korean_ratio: float
    broken_char_ratio: float
    blocks_per_page: float
    heading_ratio: float
    valid_table_ratio: float
    structural_chunk_ratio: float
    total_chunks: int
    avg_tokens: float


class QualityGateResult(BaseModel):
    """품질 게이트 판정 결과 VO.

    frozen=True → 생성 후 불변 (Value Object 원칙)

    처리 상태:
        success                    — 추출 품질 양호, 결과 전달
        warning                    — 일부 구조 불확실, 결과 전달 + 검수 표시
        manual_correction_required — 자동 해석 불안정, 에러코드와 함께 반환
        failed                     — 파싱 완전 불가, 재업로드 요청

    Attributes:
        quality_status: 품질 판정 상태
        metrics: 품질 측정 지표
        warnings: 발생한 경고 목록
        error_codes: 발생한 에러코드 목록 (E0201 등)
        decision_reason: 판정 근거 설명 (선택)
    """

    model_config = ConfigDict(frozen=True)

    quality_status: Literal[
        "success",
        "warning",
        "manual_correction_required",
        "failed",
    ]
    metrics: QualityMetrics
    warnings: list[WarningInfo]
    error_codes: list[str]
    decision_reason: Optional[str] = None


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