"""
REQ-006 doc_parser — domain/services/quality_gate.py

Parser Quality Gate 서비스
모든 임계값은 config/parser_quality.yaml 에서 읽음 — 코드 내 숫자 직접 기입 금지!

처리 상태:
    success                    — 추출 품질 양호
    warning                    — 일부 구조 불확실
    manual_correction_required — 자동 해석 불안정
    failed                     — 파싱 완전 불가
"""
from __future__ import annotations

import re

from common_schemas.document import ContentBlock, DocumentBlock

from doc_parser.domain.entities.chunk import Chunk
from doc_parser.domain.entities.warning import WarningInfo
from doc_parser.domain.entities.quality import QualityGateResult, QualityMetrics


class QualityGate:
    """Parser Quality Gate 서비스.

    DocumentBlock + Chunk 목록을 받아 품질을 평가하고
    QualityGateResult VO 를 반환.

    Args:
        config: config/parser_quality.yaml 설정값
            - min_text_length: 최소 텍스트 길이
            - min_text_per_page: 페이지당 최소 텍스트 길이
            - korean_ratio_warn: 한글 비율 경고 임계값
            - broken_char_warn: 깨진 문자 비율 경고 임계값
            - blocks_per_page_warn: 페이지당 블록 수 경고 임계값
            - max_parser_warnings: 최대 허용 경고 수
            - min_heading_ratio: 최소 heading 비율
            - min_valid_table_ratio: 최소 유효 표 비율
            - min_structural_chunk_ratio: 최소 구조적 청크 비율
            - warn_threshold_count: warning → manual_correction_required 격상 기준
    """

    def __init__(self, config: dict) -> None:
        self._cfg = config

    # ──────────────────────────────────────────
    # Public
    # ──────────────────────────────────────────

    def evaluate(
        self,
        document: DocumentBlock,
        chunks: list[Chunk],
    ) -> QualityGateResult:
        """품질 게이트 평가 실행.

        Args:
            document: 파싱된 DocumentBlock
            chunks: 청킹 결과 Chunk 목록

        Returns:
            QualityGateResult: 품질 판정 결과 VO
        """
        blocks = list(document.blocks)
        full_text = self._extract_full_text(blocks)
        warnings: list[WarningInfo] = []
        error_codes: list[str] = []

        # ── 1. 텍스트 길이 검사 (failed 판정) ──
        page_count = document.file_meta.page_count or 1
        min_length = max(
            page_count * self._cfg.get("min_text_per_page", 150),
            self._cfg.get("min_text_length", 500),
        )
        if len(full_text) < min_length:
            metrics = self._calc_metrics(blocks, chunks, full_text)
            return QualityGateResult(
                quality_status="failed",
                metrics=metrics,
                warnings=[
                    WarningInfo(
                        code="E0211",
                        message="추출 텍스트 길이 부족 — 파싱 완전 불가",
                        detail={
                            "extracted_length": len(full_text),
                            "min_required": min_length,
                        },
                    )
                ],
                error_codes=["E0211"],
                decision_reason=f"텍스트 길이 {len(full_text)} < 최소 {min_length}",
            )

        # ── 2. 품질 지표 계산 ──
        metrics = self._calc_metrics(blocks, chunks, full_text)

        # ── 3. 경고 판정 ──
        warnings.extend(self._check_korean_ratio(metrics.korean_ratio))
        warnings.extend(self._check_broken_char_ratio(metrics.broken_char_ratio))
        warnings.extend(self._check_blocks_per_page(metrics.blocks_per_page))
        warnings.extend(self._check_heading_ratio(metrics.heading_ratio))
        warnings.extend(self._check_valid_table_ratio(metrics.valid_table_ratio, document))
        warnings.extend(self._check_structural_chunk_ratio(metrics.structural_chunk_ratio))

        # ── 4. 경고 누적 → manual_correction_required 격상 ──
        warn_threshold = self._cfg.get("warn_threshold_count", 3)
        if len(warnings) >= warn_threshold:
            error_codes.append("E0211")
            return QualityGateResult(
                quality_status="manual_correction_required",
                metrics=metrics,
                warnings=warnings,
                error_codes=error_codes,
                decision_reason=(
                    f"경고 {len(warnings)}건 누적 "
                    f"(임계값: {warn_threshold}건)"
                ),
            )

        # ── 5. 최종 판정 ──
        status = "warning" if warnings else "success"
        return QualityGateResult(
            quality_status=status,
            metrics=metrics,
            warnings=warnings,
            error_codes=error_codes,
        )

    # ──────────────────────────────────────────
    # Private — 지표 계산
    # ──────────────────────────────────────────

    def _calc_metrics(
        self,
        blocks: list[ContentBlock],
        chunks: list[Chunk],
        full_text: str,
    ) -> QualityMetrics:
        """전체 품질 지표 계산."""
        page_count = max(
            max((b.page or 1 for b in blocks), default=1),
            1,
        )
        total_chunks = len(chunks)
        avg_tokens = (
            sum(c.token_count for c in chunks) / total_chunks
            if total_chunks > 0
            else 0.0
        )

        return QualityMetrics(
            korean_ratio=self._calc_korean_ratio(full_text),
            broken_char_ratio=self._calc_broken_char_ratio(full_text),
            blocks_per_page=len(blocks) / page_count,
            heading_ratio=self._calc_heading_ratio(blocks),
            valid_table_ratio=self._calc_valid_table_ratio(blocks),
            structural_chunk_ratio=self._calc_structural_chunk_ratio(chunks),
            total_chunks=total_chunks,
            avg_tokens=avg_tokens,
        )

    def _calc_korean_ratio(self, text: str) -> float:
        """한글 문자 비율 계산."""
        if not text:
            return 0.0
        korean = len(re.findall(r"[가-힣]", text))
        return korean / len(text)

    def _calc_broken_char_ratio(self, text: str) -> float:
        """깨진 문자(replacement character 등) 비율 계산."""
        if not text:
            return 0.0
        broken = len(re.findall(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f]", text))
        return broken / len(text)

    def _calc_heading_ratio(self, blocks: list[ContentBlock]) -> float:
        """전체 블록 중 heading 블록 비율."""
        if not blocks:
            return 0.0
        headings = sum(1 for b in blocks if b.block_type == "heading")
        return headings / len(blocks)

    def _calc_valid_table_ratio(self, blocks: list[ContentBlock]) -> float:
        """유효한 표(2행 이상, 2열 이상) 비율."""
        table_blocks = [b for b in blocks if b.block_type == "table"]
        if not table_blocks:
            return 1.0  # 표 없으면 해당 없음 → 1.0

        valid = sum(
            1
            for b in table_blocks
            if b.table and len(b.table) >= 2 and len(b.table[0]) >= 2
        )
        return valid / len(table_blocks)

    def _calc_structural_chunk_ratio(self, chunks: list[Chunk]) -> float:
        """구조적 청크(structural) 비율."""
        if not chunks:
            return 0.0
        structural = sum(1 for c in chunks if c.chunk_type == "structural")
        return structural / len(chunks)

    # ──────────────────────────────────────────
    # Private — 경고 판정
    # ──────────────────────────────────────────

    def _check_korean_ratio(self, ratio: float) -> list[WarningInfo]:
        threshold = self._cfg.get("korean_ratio_warn", 0.30)
        if ratio < threshold:
            return [
                WarningInfo(
                    code="W0201",
                    message=f"한글 비율 낮음: {ratio:.2%} (기준: {threshold:.2%})",
                    detail={"korean_ratio": ratio, "threshold": threshold},
                )
            ]
        return []

    def _check_broken_char_ratio(self, ratio: float) -> list[WarningInfo]:
        threshold = self._cfg.get("broken_char_warn", 0.10)
        if ratio > threshold:
            return [
                WarningInfo(
                    code="W0202",
                    message=f"깨진 문자 비율 높음: {ratio:.2%} (기준: {threshold:.2%})",
                    detail={"broken_char_ratio": ratio, "threshold": threshold},
                )
            ]
        return []

    def _check_blocks_per_page(self, bpp: float) -> list[WarningInfo]:
        threshold = self._cfg.get("blocks_per_page_warn", 1.0)
        if bpp < threshold:
            return [
                WarningInfo(
                    code="W0203",
                    message=f"페이지당 블록 수 부족: {bpp:.1f} (기준: {threshold:.1f})",
                    detail={"blocks_per_page": bpp, "threshold": threshold},
                )
            ]
        return []

    def _check_heading_ratio(self, ratio: float) -> list[WarningInfo]:
        threshold = self._cfg.get("min_heading_ratio", 0.05)
        if ratio < threshold:
            return [
                WarningInfo(
                    code="W0204",
                    message=f"섹션 구조 감지율 낮음: {ratio:.2%} (기준: {threshold:.2%})",
                    detail={"heading_ratio": ratio, "threshold": threshold},
                )
            ]
        return []

    def _check_valid_table_ratio(
        self,
        ratio: float,
        document: DocumentBlock,
    ) -> list[WarningInfo]:
        threshold = self._cfg.get("min_valid_table_ratio", 0.80)
        if ratio < threshold:
            # 하네스 문서 여부에 따라 등급 다름 (is_harness_doc → E0204)
            return [
                WarningInfo(
                    code="E0204",
                    message=f"표 헤더 유효성 낮음: {ratio:.2%} (기준: {threshold:.2%})",
                    detail={"valid_table_ratio": ratio, "threshold": threshold},
                )
            ]
        return []

    def _check_structural_chunk_ratio(self, ratio: float) -> list[WarningInfo]:
        threshold = self._cfg.get("min_structural_chunk_ratio", 0.30)
        if ratio < threshold:
            return [
                WarningInfo(
                    code="W0205",
                    message=f"구조적 청크 비율 낮음: {ratio:.2%} (기준: {threshold:.2%})",
                    detail={"structural_chunk_ratio": ratio, "threshold": threshold},
                )
            ]
        return []

    # ──────────────────────────────────────────
    # Private — 유틸
    # ──────────────────────────────────────────

    def _extract_full_text(self, blocks: list[ContentBlock]) -> str:
        """전체 블록에서 텍스트 추출."""
        return " ".join(b.content or "" for b in blocks if b.content)