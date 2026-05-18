"""
REQ-006 doc_parser — adapters/interleaving_parser.py

InterleavingParser
텍스트 파싱 + 비전 모드 인터리빙 지휘자

수정 방향:
    - DOCX는 기본적으로 XML 기반 DocxParser 결과를 신뢰한다.
    - DOCX를 "전체 1장 찰칵" 대상으로 넣지 않는다.
    - HWP만 full-page fallback 대상으로 유지한다.
    - PDF/HWPX/PPTX는 감지 후 선택적으로 비전 호출한다.
    - CSV/MD는 비전 스킵한다.

중요:
    DOCX는 내부적으로 고정 page 개념이 없으므로 page 기반 vision을 기본으로 쓰지 않는다.
    DOCX에서 비전이 필요하면 별도 deep-mode 또는 image/object fallback으로 분리하는 것이 안전하다.
"""
from __future__ import annotations

from common_schemas.document import (
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
)

from doc_parser.adapters.vision.table_detector import TableDetector
from doc_parser.domain.entities.vision_type import VisionType
from doc_parser.domain.ports.parser_port import ParserPort
from doc_parser.domain.ports.vision_port import VisionPort


# 비전 스킵 포맷
_VISION_SKIP_MIME = {
    "text/csv",
    "text/markdown",
}

# 전체 페이지 찰칵 포맷
# NOTE:
#   DOCX는 여기서 제거한다.
#   DOCX는 python-docx XML 순회로 본문/표를 모두 긁어오는 것이 기본 전략이다.
_FULL_PAGE_MIME = {
    "application/x-hwp",
}

# DOCX MIME
_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument"
    ".wordprocessingml.document"
)


class InterleavingParser(ParserPort):
    """텍스트 + 비전 인터리빙 파서."""

    def __init__(
        self,
        base_parser: ParserPort,
        table_detector: TableDetector,
        vision_extractor: VisionPort,
    ) -> None:
        self._base_parser = base_parser
        self._table_detector = table_detector
        self._vision_extractor = vision_extractor

    def parse(
        self,
        file_path: str,
        file_meta: FileMeta,
    ) -> DocumentBlock:
        """인터리빙 파싱 → DocumentBlock 반환."""
        mime_type = file_meta.mime_type or ""

        # 그룹 D: 비전 스킵
        if mime_type in _VISION_SKIP_MIME:
            return self._base_parser.parse(file_path, file_meta)

        # 1. BaseParser로 텍스트/구조 추출
        base_doc = self._base_parser.parse(file_path, file_meta)

        # DOCX:
        #   page 기반 vision을 기본으로 붙이지 않는다.
        #   DocxParser가 문단/표를 원문 순서대로 뽑는 것이 우선이다.
        if mime_type == _DOCX_MIME:
            return self._rebuild_doc(base_doc, list(base_doc.blocks), file_meta)

        # HWP:
        #   현재 HWP는 구조 파싱이 까다로우므로 full-page fallback 유지
        if mime_type in _FULL_PAGE_MIME:
            return self._parse_full_page(file_path, file_meta, base_doc)

        # PDF/HWPX/PPTX:
        #   감지 후 선택적으로 비전 호출
        return self._parse_interleaving(file_path, file_meta, base_doc)

    def supports(self, mime_type: str) -> bool:
        return self._base_parser.supports(mime_type)

    def _parse_interleaving(
        self,
        file_path: str,
        file_meta: FileMeta,
        base_doc: DocumentBlock,
    ) -> DocumentBlock:
        """블록 스트림 흐르다가 비전 필요 시 찰칵.

        페이지당 최대 1회 비전 호출.
        """
        result_blocks: list[ContentBlock] = []
        captured_pages: set[int] = set()

        for block in base_doc.blocks:
            vision_type = self._table_detector.detect(block)

            if vision_type is None:
                result_blocks.append(block)
                continue

            page_num = block.page or 1

            if page_num in captured_pages:
                result_blocks.append(block)
                continue

            vision_block = self._vision_extractor.extract(
                file_path=file_path,
                vision_type=vision_type,
                page_num=page_num,
                block_index=len(result_blocks),
            )

            captured_pages.add(page_num)

            if vision_block:
                # 기존 블록을 날려버리면 원문 손실 위험이 있으므로
                # 원문 블록 + 비전 보조 블록을 모두 보존한다.
                result_blocks.append(block)
                result_blocks.append(vision_block)
            else:
                result_blocks.append(block)

        return self._rebuild_doc(base_doc, result_blocks, file_meta)

    def _parse_full_page(
        self,
        file_path: str,
        file_meta: FileMeta,
        base_doc: DocumentBlock,
    ) -> DocumentBlock:
        """전체 페이지 fallback.

        현재는 HWP 전용에 가깝게 사용한다.
        DOCX는 이 경로로 보내지 않는다.
        """
        result_blocks: list[ContentBlock] = list(base_doc.blocks)

        vision_block = self._vision_extractor.extract(
            file_path=file_path,
            vision_type=VisionType.FULL_PAGE,
            page_num=1,
            block_index=len(result_blocks),
        )

        if vision_block:
            result_blocks.append(vision_block)

        return self._rebuild_doc(base_doc, result_blocks, file_meta)

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
                parser_version="1.1.0",
            ),
            blocks=blocks,
        )
