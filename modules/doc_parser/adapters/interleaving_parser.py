"""
REQ-006 doc_parser — adapters/interleaving_parser.py

InterleavingParser
텍스트 파싱 + 비전 모드 인터리빙 지휘자

처리 전략:
    - CSV/MD: 비전 스킵 (구조적 텍스트로 충분)
    - 나머지 전부: _parse_interleaving() 하나로 통일
        TableDetector가 블록 보고 TABLE / GRAPH / CHART / CORRUPTED 판단
        감지 없으면 텍스트 그대로 통과

포맷별 비전 불필요 판단 (포맷 분기 없이 자연스럽게 처리):
    - DOCX: XML 순회로 본문/표 추출 → 텍스트 블록으로 흘러오므로 비전 감지 없음
    - HWP: hwp5html/hwp5txt로 추출 → 동일하게 텍스트 블록으로 흘러옴
    - XLSX: 3층 구조 파서가 처리 → 차트/이미지는 CHART 타입으로 감지
"""
from __future__ import annotations

from common_schemas.document import (
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
)

from doc_parser.adapters.vision.table_detector import TableDetector
from doc_parser.domain.ports.parser_port import ParserPort
from doc_parser.domain.ports.vision_port import VisionPort


# 비전 스킵 포맷
_VISION_SKIP_MIME = {
    "text/csv",
    "text/markdown",
}


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

        # 2. 블록 스트림 흘리며 비전 필요 시 찰칵
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
        vision_count: int = 0
        failed_count: int = 0

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
                vision_count += 1
            else:
                result_blocks.append(block)
                failed_count += 1

        return self._rebuild_doc(base_doc, result_blocks, vision_count, failed_count)

    def _rebuild_doc(
        self,
        base_doc: DocumentBlock,
        blocks: list[ContentBlock],
        vision_count: int = 0,
        failed_count: int = 0,
    ) -> DocumentBlock:
        """새 블록 목록으로 DocumentBlock 재조립.

        file_meta는 base_doc의 것을 보존한다 — 인자로 받은 원본 file_meta가 아니라
        base_parser가 파싱 중 보강한 값(예: PdfParser가 채운 page_count)을 그대로
        흘려보내기 위함. 원본 file_meta로 덮어쓰면 page_count 보강이 소실되어
        QualityGate `_calc_coverage`의 total_pages가 0이 된다.
        """
        return DocumentBlock(
            document_id=base_doc.document_id,
            file_meta=base_doc.file_meta,
            parser=ParserMeta(
                parser_name=f"Interleaving({base_doc.parser.parser_name})",
                parser_version="1.1.0",
            ),
            blocks=blocks,
            vision_block_count=vision_count,
            failed_block_count=failed_count,
        )
