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
from doc_parser.domain.entities.quality import (
    ParseCoverage,
    QualityConfig,
    QualityGateResult,
    QualityMetrics,
)
from doc_parser.domain.entities.warning import WarningInfo


class QualityGate:
    """Parser Quality Gate 서비스 (stateless).

    DocumentBlock + Chunk 목록 + QualityConfig 를 받아 품질을 평가하고
    QualityGateResult VO 를 반환.

    config 는 application layer(ParsingPipeline)가 로드하여 주입 —
    Clean Architecture 원칙에 따라 domain service는 stateless 유지.
    """

    # ──────────────────────────────────────────
    # Public
    # ──────────────────────────────────────────

    def evaluate(
        self,
        document: DocumentBlock,
        chunks: list[Chunk],
        config: QualityConfig,
    ) -> QualityGateResult:
        """품질 게이트 평가 실행.

        Args:
            document: 파싱된 DocumentBlock
            chunks: 청킹 결과 Chunk 목록
            config: 품질 게이트 설정 (application layer에서 주입)

        Returns:
            QualityGateResult: 품질 판정 결과 VO
        """
        blocks = list(document.blocks)
        full_text = self._extract_full_text(blocks)
        warnings: list[WarningInfo] = []
        error_codes: list[str] = []

        # ── 커버리지 계산 (모든 반환 지점에서 공유) ──
        coverage = self._calc_coverage(document, blocks)

        # ── 1. 텍스트 길이 검사 (failed 판정) ──
        page_count = document.file_meta.page_count or 1
        min_length = max(
            page_count * config.min_text_per_page,
            config.min_text_length,
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
                coverage=coverage,
            )

        # ── 2. 품질 지표 계산 ──
        metrics = self._calc_metrics(blocks, chunks, full_text)

        # ── 3. 경고 판정 ──
        warnings.extend(self._check_korean_ratio(metrics.korean_ratio, config))
        warnings.extend(self._check_broken_char_ratio(metrics.broken_char_ratio, config))
        warnings.extend(self._check_blocks_per_page(metrics.blocks_per_page, config))
        warnings.extend(self._check_heading_ratio(metrics.heading_ratio, config))
        warnings.extend(self._check_valid_table_ratio(metrics.valid_table_ratio, document, config))
        warnings.extend(self._check_structural_chunk_ratio(metrics.structural_chunk_ratio, config))

        # ── 4. 경고 누적 → manual_correction_required 격상 ──
        if len(warnings) >= config.warn_threshold_count:
            error_codes.append("E0211")
            return QualityGateResult(
                quality_status="manual_correction_required",
                metrics=metrics,
                warnings=warnings,
                error_codes=error_codes,
                decision_reason=(
                    f"경고 {len(warnings)}건 누적 "
                    f"(임계값: {config.warn_threshold_count}건)"
                ),
                coverage=coverage,
            )

        # ── 5. 최종 판정 ──
        status = "warning" if warnings else "success"
        return QualityGateResult(
            quality_status=status,
            metrics=metrics,
            warnings=warnings,
            error_codes=error_codes,
            coverage=coverage,
        )

    # ──────────────────────────────────────────
    # Private — 커버리지 계산
    # ──────────────────────────────────────────

    def _calc_coverage(
        self,
        document: DocumentBlock,
        blocks: list[ContentBlock],
    ) -> ParseCoverage:
        """파싱 커버리지 계산.

        QualityGate 담당 필드:
            total_pages   → FileMeta.page_count
            parsed_pages  → blocks 에서 실제 등장한 page 집합
            text_blocks   → block_type in ("text", "heading") 집계
            table_blocks  → block_type == "table" 집계
            warnings      → 커버리지 이상 감지 시 메시지 추가

        Skeleton 필드 (InterleavingParser 연결 후 채움):
            vision_blocks → 0 고정
            failed_blocks → 0 고정

        Args:
            document: 파싱된 DocumentBlock
            blocks: 전체 ContentBlock 목록

        Returns:
            ParseCoverage
        """
        total_pages = document.file_meta.page_count or 0
        parsed_pages = len({b.page for b in blocks if b.page is not None})
        text_blocks = sum(
            1 for b in blocks if b.block_type in ("text", "heading")
        )
        table_blocks = sum(
            1 for b in blocks if b.block_type == "table"
        )

        coverage_warnings: list[str] = []
        if total_pages > 0 and parsed_pages < total_pages:
            coverage_warnings.append(
                f"파싱 누락 페이지 감지: {parsed_pages}/{total_pages} 페이지 파싱됨"
            )
        if not blocks:
            coverage_warnings.append("추출된 블록 없음")

        return ParseCoverage(
            total_pages=total_pages,
            parsed_pages=parsed_pages,
            text_blocks=text_blocks,
            table_blocks=table_blocks,
            vision_blocks=document.vision_block_count,
            failed_blocks=document.failed_block_count,
            warnings=coverage_warnings,
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
        """유효한 표 비율 계산.

        유효 표 기준: 2행 이상, 2열 이상.

        XLSX 병합셀 구조 분기:
            block.metadata 존재 시 → metadata["data_rows"] / ["normalized_headers"] 기준으로 유효성 판단
            metadata 없음 → 기존 flat rows 처리
        """
        table_blocks = [b for b in blocks if b.block_type == "table"]
        if not table_blocks:
            return 1.0  # 표 없으면 해당 없음 → 1.0

        valid = 0
        for b in table_blocks:
            if not b.table:
                continue
            # XLSX 병합셀 구조: metadata에 data_rows/normalized_headers 포함
            if b.metadata is not None:
                data_rows = b.metadata.get("data_rows", [])
                normalized_headers = b.metadata.get("normalized_headers", [])
                is_valid = len(data_rows) >= 1 and len(normalized_headers) >= 2
            else:
                is_valid = len(b.table) >= 2 and len(b.table[0]) >= 2
            if is_valid:
                valid += 1

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

    def _check_korean_ratio(self, ratio: float, config: QualityConfig) -> list[WarningInfo]:
        threshold = config.korean_ratio_warn
        if ratio < threshold:
            return [
                WarningInfo(
                    code="W0201",
                    message=f"한글 비율 낮음: {ratio:.2%} (기준: {threshold:.2%})",
                    detail={"korean_ratio": ratio, "threshold": threshold},
                )
            ]
        return []

    def _check_broken_char_ratio(self, ratio: float, config: QualityConfig) -> list[WarningInfo]:
        threshold = config.broken_char_warn
        if ratio > threshold:
            return [
                WarningInfo(
                    code="W0202",
                    message=f"깨진 문자 비율 높음: {ratio:.2%} (기준: {threshold:.2%})",
                    detail={"broken_char_ratio": ratio, "threshold": threshold},
                )
            ]
        return []

    def _check_blocks_per_page(self, bpp: float, config: QualityConfig) -> list[WarningInfo]:
        threshold = config.blocks_per_page_warn
        if bpp < threshold:
            return [
                WarningInfo(
                    code="W0203",
                    message=f"페이지당 블록 수 부족: {bpp:.1f} (기준: {threshold:.1f})",
                    detail={"blocks_per_page": bpp, "threshold": threshold},
                )
            ]
        return []

    def _check_heading_ratio(self, ratio: float, config: QualityConfig) -> list[WarningInfo]:
        threshold = config.min_heading_ratio
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
        config: QualityConfig,
    ) -> list[WarningInfo]:
        threshold = config.min_valid_table_ratio
        if ratio < threshold:
            # TODO: is_harness_doc 분기 추가 (황대원님 협의 필요)
            return [
                WarningInfo(
                    code="E0204",
                    message=f"표 헤더 유효성 낮음: {ratio:.2%} (기준: {threshold:.2%})",
                    detail={"valid_table_ratio": ratio, "threshold": threshold},
                )
            ]
        return []

    def _check_structural_chunk_ratio(self, ratio: float, config: QualityConfig) -> list[WarningInfo]:
        threshold = config.min_structural_chunk_ratio
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
