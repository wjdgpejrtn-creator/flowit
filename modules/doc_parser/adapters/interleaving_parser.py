"""
REQ-006 doc_parser — adapters/interleaving_parser.py

InterleavingParser
텍스트 파싱 + 비전 모드 인터리빙 지휘자

처리 흐름:
    BaseParser 스트림 쫘라라락
      → TableDetector.detect(block)
          → None        : 텍스트 그대로 ✅
          → VisionType  : 찰칵📸 → VisionExtractor → ContentBlock

포맷별 전략:
    그룹 A (감지 후 찰칵): PDF, HWPX, PPTX
        → 블록 스트림 흐르다가 표/이미지 감지 시 해당 페이지 찰칵
    그룹 B (전체 찰칵):   DOCX, HWP
        → 페이지 단위 전체 찰칵 + 텍스트 병행
    그룹 C (3층 구조):    XLSX
        → 기존 XlsxParser 유지 (별도 처리)
    그룹 D (비전 스킵):   CSV, MD
        → BaseParser 결과 그대로 반환

페이지당 최대 1번 찰칵 원칙:
    같은 페이지에서 표/그래프가 여러 개 감지되어도
    해당 페이지는 1번만 찰칵📸 (중복 캡처 방지)
"""
from __future__ import annotations

from uuid import uuid4

from common_schemas.document import (
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
)

from doc_parser.adapters.vision.table_detector import TableDetector
from doc_parser.adapters.vision.vision_extractor import VisionExtractor
from doc_parser.domain.entities.vision_type import VisionType
from doc_parser.domain.ports.parser_port import ParserPort
from doc_parser.domain.ports.vision_port import VisionPort

# 비전 스킵 포맷 (그룹 D)
_VISION_SKIP_MIME = {
    "text/csv",
    "text/markdown",
}

# 전체 페이지 찰칵 포맷 (그룹 B)
_FULL_PAGE_MIME = {
    "application/x-hwp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class InterleavingParser(ParserPort):
    """텍스트 + 비전 인터리빙 파서.

    ParserFactory가 BaseParser + TableDetector + VisionExtractor를
    조립해서 반환하는 래퍼 파서.

    Args:
        base_parser: 포맷별 BaseParser (텍스트 추출 담당)
        table_detector: 에엥? 감지 담당
        vision_extractor: 찰칵📸 + Gemma4 담당

    Example:
        parser = InterleavingParser(
            base_parser=HwpParser(),
            table_detector=TableDetector(broken_char_threshold=0.3),
            vision_extractor=VisionExtractor(llm=LLMBase()),
        )
        doc = parser.parse(file_path, file_meta)
    """

    def __init__(
        self,
        base_parser: ParserPort,
        table_detector: TableDetector,
        vision_extractor: VisionPort,
    ) -> None:
        self._base_parser = base_parser
        self._table_detector = table_detector
        self._vision_extractor = vision_extractor

    # ──────────────────────────────────────────
    # ParserPort 구현
    # ──────────────────────────────────────────

    def parse(
        self,
        file_path: str,
        file_meta: FileMeta,
    ) -> DocumentBlock:
        """인터리빙 파싱 → DocumentBlock 반환.

        Args:
            file_path: 파일 경로
            file_meta: 파일 메타데이터

        Returns:
            DocumentBlock: 텍스트 + 비전 블록이 인터리빙된 문서
        """
        mime_type = file_meta.mime_type or ""

        # ── 그룹 D: 비전 스킵 ──
        if mime_type in _VISION_SKIP_MIME:
            return self._base_parser.parse(file_path, file_meta)

        # ── 1. BaseParser로 텍스트 추출 ──
        base_doc = self._base_parser.parse(file_path, file_meta)

        # ── 그룹 B: 전체 페이지 찰칵 ──
        if mime_type in _FULL_PAGE_MIME:
            return self._parse_full_page(file_path, file_meta, base_doc)

        # ── 그룹 A: 감지 후 찰칵 (인터리빙) ──
        return self._parse_interleaving(file_path, file_meta, base_doc)

    def supports(self, mime_type: str) -> bool:
        return self._base_parser.supports(mime_type)

    # ──────────────────────────────────────────
    # Private — 그룹 A: 인터리빙
    # ──────────────────────────────────────────

    def _parse_interleaving(
        self,
        file_path: str,
        file_meta: FileMeta,
        base_doc: DocumentBlock,
    ) -> DocumentBlock:
        """블록 스트림 흐르다가 에엥? 감지 시 찰칵📸.

        페이지당 최대 1번 찰칵 원칙 적용.
        """
        result_blocks: list[ContentBlock] = []
        captured_pages: set[int] = set()  # 이미 찰칵한 페이지 추적

        for block in base_doc.blocks:
            vision_type = self._table_detector.detect(block)

            if vision_type is None:
                # 정상 텍스트 → 그냥 쫘라라락
                result_blocks.append(block)
                continue

            page_num = block.page or 1

            # 이미 찰칵한 페이지면 스킵 (중복 방지)
            if page_num in captured_pages:
                result_blocks.append(block)
                continue

            # 찰칵📸
            vision_block = self._vision_extractor.extract(
                file_path=file_path,
                vision_type=vision_type,
                page_num=page_num,
                block_index=len(result_blocks),
            )

            captured_pages.add(page_num)

            if vision_block:
                # 비전 블록으로 교체
                result_blocks.append(vision_block)
            else:
                # 비전 실패 → 원본 텍스트 블록 유지 + warning
                result_blocks.append(block)

        return self._rebuild_doc(base_doc, result_blocks, file_meta)

    # ──────────────────────────────────────────
    # Private — 그룹 B: 전체 페이지 찰칵
    # ──────────────────────────────────────────

    def _parse_full_page(
        self,
        file_path: str,
        file_meta: FileMeta,
        base_doc: DocumentBlock,
    ) -> DocumentBlock:
        """전체 페이지를 찰칵📸 + 텍스트 병행.

        DOCX/HWP 전략:
            페이지 경계를 모르므로 전체를 1장으로 찰칵.
            텍스트 추출 결과 + 비전 결과를 합쳐서 반환.
        """
        result_blocks: list[ContentBlock] = list(base_doc.blocks)

        # 전체 문서를 1장으로 찰칵📸
        vision_block = self._vision_extractor.extract(
            file_path=file_path,
            vision_type=VisionType.FULL_PAGE,
            page_num=1,
            block_index=len(result_blocks),
        )

        if vision_block:
            result_blocks.append(vision_block)

        return self._rebuild_doc(base_doc, result_blocks, file_meta)

    # ──────────────────────────────────────────
    # Private — DocumentBlock 재조립
    # ──────────────────────────────────────────

    def _rebuild_doc(
        self,
        base_doc: DocumentBlock,
        blocks: list[ContentBlock],
        file_meta: FileMeta,
    ) -> DocumentBlock:
        """새 블록 목록으로 DocumentBlock 재조립."""
        return DocumentBlock(
            document_id=base_doc.document_id,
            file_meta=file_meta,
            parser=ParserMeta(
                parser_name=f"Interleaving({base_doc.parser.parser_name})",
                parser_version="1.0.0",
            ),
            blocks=blocks,
        )
