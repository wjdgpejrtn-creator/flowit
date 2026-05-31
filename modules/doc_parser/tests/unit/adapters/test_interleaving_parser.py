"""
REQ-006 doc_parser — tests/unit/adapters/test_interleaving_parser.py

InterleavingParser 유닛 테스트

의존성 처리:
    TableDetector  → MagicMock (detect() 반환값 제어)
    VisionExtractor → MagicMock (extract() 반환값 제어)
    BaseParser     → MagicMock (parse() 반환값 제어)

Gemma4 / LibreOffice 미연결 상태에서도 전부 통과해야 함.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from common_schemas.document import (
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
    SourceRef,
)

from doc_parser.adapters.interleaving_parser import InterleavingParser
from doc_parser.domain.entities.vision_type import VisionType


# ──────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────

def _make_file_meta(mime_type: str) -> FileMeta:
    return FileMeta(
        file_name="test.docx",
        file_type="docx",
        mime_type=mime_type,
        file_size=1024,
        page_count=1,
    )


def _make_text_block(page: int = 1, content: str = "정상 텍스트") -> ContentBlock:
    return ContentBlock(
        block_id=uuid4(),
        block_type="text",
        content=content,
        page=page,
        source_ref=SourceRef(page=page, block_index=0),
    )


def _make_table_block(page: int = 1) -> ContentBlock:
    return ContentBlock(
        block_id=uuid4(),
        block_type="table",
        content=None,
        page=page,
        table=[["헤더1", "헤더2"], ["값1", "값2"]],
        source_ref=SourceRef(page=page, block_index=0),
    )


def _make_vision_block(page: int = 1) -> ContentBlock:
    return ContentBlock(
        block_id=uuid4(),
        block_type="table",
        content="비전 추출 결과",
        page=page,
        source_ref=SourceRef(page=page, block_index=0),
    )


def _make_base_doc(
    blocks: list[ContentBlock],
    mime_type: str = "application/pdf",
) -> DocumentBlock:
    return DocumentBlock(
        document_id=uuid4(),
        file_meta=_make_file_meta(mime_type),
        parser=ParserMeta(parser_name="PdfParser", parser_version="1.0.0"),
        blocks=blocks,
    )


def _make_parser(
    base_doc: DocumentBlock,
    detect_returns: list,           # detect() 순서대로 반환값 목록
    extract_return=None,            # extract() 반환값 (단일 고정값)
) -> tuple[InterleavingParser, MagicMock, MagicMock, MagicMock]:
    """InterleavingParser + Mock 3종 조립 헬퍼."""
    base_parser = MagicMock()
    base_parser.parse.return_value = base_doc
    base_parser.supports.return_value = True

    detector = MagicMock()
    detector.detect.side_effect = detect_returns

    extractor = MagicMock()
    extractor.extract.return_value = extract_return

    parser = InterleavingParser(
        base_parser=base_parser,
        table_detector=detector,
        vision_extractor=extractor,
    )
    return parser, base_parser, detector, extractor


# ──────────────────────────────────────────
# 테스트
# ──────────────────────────────────────────

class TestInterleavingParser:

    def test_텍스트블록_비전스킵(self):
        """정상 텍스트 블록은 VisionExtractor 호출 없이 그대로 통과."""
        block = _make_text_block(page=1, content="정상 텍스트")
        base_doc = _make_base_doc([block])
        file_meta = _make_file_meta("application/pdf")

        parser, _, detector, extractor = _make_parser(
            base_doc=base_doc,
            detect_returns=[None],   # 비전 불필요
        )

        result = parser.parse("test.pdf", file_meta)

        assert len(result.blocks) == 1
        assert result.blocks[0].content == "정상 텍스트"
        extractor.extract.assert_not_called()

    def test_표블록_비전트리거(self):
        """block_type=table 감지 시 VisionExtractor.extract() 호출, 원본+비전 블록 모두 보존."""
        table_block = _make_table_block(page=1)
        vision_block = _make_vision_block(page=1)
        base_doc = _make_base_doc([table_block])
        file_meta = _make_file_meta("application/pdf")

        parser, _, detector, extractor = _make_parser(
            base_doc=base_doc,
            detect_returns=[VisionType.TABLE],
            extract_return=vision_block,
        )

        result = parser.parse("test.pdf", file_meta)

        extractor.extract.assert_called_once_with(
            file_path="test.pdf",
            vision_type=VisionType.TABLE,
            page_num=1,
            block_index=0,
        )
        # 원본 블록 + 비전 블록 모두 보존
        assert len(result.blocks) == 2
        assert result.blocks[0].block_id == table_block.block_id
        assert result.blocks[1].content == "비전 추출 결과"

    def test_페이지당_1번만_찰칵(self):
        """같은 페이지에 표가 2개 있어도 VisionExtractor는 1번만 호출."""
        block1 = _make_table_block(page=1)
        block2 = _make_table_block(page=1)
        vision_block = _make_vision_block(page=1)
        base_doc = _make_base_doc([block1, block2])
        file_meta = _make_file_meta("application/pdf")

        parser, _, detector, extractor = _make_parser(
            base_doc=base_doc,
            detect_returns=[VisionType.TABLE, VisionType.TABLE],
            extract_return=vision_block,
        )

        result = parser.parse("test.pdf", file_meta)

        # 추출은 1번만
        extractor.extract.assert_called_once()
        # 블록은 3개 (첫 번째 원본 + 비전 + 두 번째 원본은 페이지 스킵 후 그대로 통과)
        assert len(result.blocks) == 3

    def test_비전실패시_원본유지(self):
        """VisionExtractor.extract()가 None 반환하면 원본 블록 유지."""
        table_block = _make_table_block(page=1)
        base_doc = _make_base_doc([table_block])
        file_meta = _make_file_meta("application/pdf")

        parser, _, detector, extractor = _make_parser(
            base_doc=base_doc,
            detect_returns=[VisionType.TABLE],
            extract_return=None,     # 비전 실패
        )

        result = parser.parse("test.pdf", file_meta)

        # 원본 블록 유지
        assert len(result.blocks) == 1
        assert result.blocks[0].block_id == table_block.block_id

    def test_비전스킵포맷_CSV(self):
        """CSV는 base_parser.parse() 결과를 그대로 반환."""
        block = _make_text_block()
        base_doc = _make_base_doc([block], mime_type="text/csv")
        file_meta = _make_file_meta("text/csv")

        parser, base_parser, detector, extractor = _make_parser(
            base_doc=base_doc,
            detect_returns=[],
        )

        result = parser.parse("test.csv", file_meta)

        # BaseParser 결과 그대로
        assert result is base_doc
        # detect / extract 호출 없음
        detector.detect.assert_not_called()
        extractor.extract.assert_not_called()

    def test_비전스킵포맷_MD(self):
        """Markdown은 base_parser.parse() 결과를 그대로 반환."""
        block = _make_text_block()
        base_doc = _make_base_doc([block], mime_type="text/markdown")
        file_meta = _make_file_meta("text/markdown")

        parser, base_parser, detector, extractor = _make_parser(
            base_doc=base_doc,
            detect_returns=[],
        )

        result = parser.parse("test.md", file_meta)

        assert result is base_doc
        detector.detect.assert_not_called()
        extractor.extract.assert_not_called()

    def test_parser_name_인터리빙_표기(self):
        """결과 DocumentBlock의 parser_name이 'Interleaving(...)' 형식."""
        block = _make_text_block()
        base_doc = _make_base_doc([block])
        file_meta = _make_file_meta("application/pdf")

        parser, _, _, _ = _make_parser(
            base_doc=base_doc,
            detect_returns=[None],
        )

        result = parser.parse("test.pdf", file_meta)

        assert result.parser.parser_name.startswith("Interleaving(")

    def test_여러페이지_각각_1번씩_찰칵(self):
        """서로 다른 페이지면 각각 찰칵📸 (페이지당 1번 원칙)."""
        block_p1 = _make_table_block(page=1)
        block_p2 = _make_table_block(page=2)
        vision_p1 = _make_vision_block(page=1)
        vision_p2 = _make_vision_block(page=2)
        base_doc = _make_base_doc([block_p1, block_p2])
        file_meta = _make_file_meta("application/pdf")

        extractor = MagicMock()
        extractor.extract.side_effect = [vision_p1, vision_p2]

        detector = MagicMock()
        detector.detect.side_effect = [VisionType.TABLE, VisionType.TABLE]

        base_parser = MagicMock()
        base_parser.parse.return_value = base_doc
        base_parser.supports.return_value = True

        parser = InterleavingParser(
            base_parser=base_parser,
            table_detector=detector,
            vision_extractor=extractor,
        )

        result = parser.parse("test.pdf", file_meta)

        # 페이지 2개 → extract 2번
        assert extractor.extract.call_count == 2
        assert len(result.blocks) == 4  # 원본 2 + 비전 2

    def test_비전성공_카운트_반영(self):
        """비전 추출 성공 시 vision_block_count가 DocumentBlock에 반영된다."""
        block_p1 = _make_table_block(page=1)
        block_p2 = _make_table_block(page=2)
        vision_p1 = _make_vision_block(page=1)
        vision_p2 = _make_vision_block(page=2)
        base_doc = _make_base_doc([block_p1, block_p2])
        file_meta = _make_file_meta("application/pdf")

        extractor = MagicMock()
        extractor.extract.side_effect = [vision_p1, vision_p2]

        detector = MagicMock()
        detector.detect.side_effect = [VisionType.TABLE, VisionType.TABLE]

        base_parser = MagicMock()
        base_parser.parse.return_value = base_doc
        base_parser.supports.return_value = True

        parser = InterleavingParser(
            base_parser=base_parser,
            table_detector=detector,
            vision_extractor=extractor,
        )

        result = parser.parse("test.pdf", file_meta)

        assert result.vision_block_count == 2
        assert result.failed_block_count == 0

    def test_비전실패_카운트_반영(self):
        """비전 추출 실패(None) 시 failed_block_count가 DocumentBlock에 반영된다."""
        block_p1 = _make_table_block(page=1)
        block_p2 = _make_table_block(page=2)
        base_doc = _make_base_doc([block_p1, block_p2])
        file_meta = _make_file_meta("application/pdf")

        parser, _, detector, extractor = _make_parser(
            base_doc=base_doc,
            detect_returns=[VisionType.TABLE, VisionType.TABLE],
            extract_return=None,  # 전부 실패
        )

        result = parser.parse("test.pdf", file_meta)

        assert result.vision_block_count == 0
        assert result.failed_block_count == 2

    def test_base_doc_file_meta_보존_page_count(self):
        """재조립 시 base_parser가 보강한 file_meta(page_count 등)를 보존한다.

        회귀: 과거엔 인자 file_meta로 덮어써서 PdfParser가 채운 page_count가 소실 →
        QualityGate total_pages=0 버그. base_doc.file_meta를 흘려보내야 한다.
        """
        block = _make_table_block(page=1)
        vision_block = _make_vision_block(page=1)
        # base_parser가 page_count=3으로 보강한 file_meta를 반환하는 상황 모사.
        enriched = _make_file_meta("application/pdf").model_copy(update={"page_count": 3})
        base_doc = DocumentBlock(
            document_id=uuid4(),
            file_meta=enriched,
            parser=ParserMeta(parser_name="PdfParser", parser_version="1.0.0"),
            blocks=[block],
        )
        # parse()에 넘기는 원본 file_meta는 page_count=1 (보강 전).
        input_meta = _make_file_meta("application/pdf")

        parser, _, _, _ = _make_parser(
            base_doc=base_doc,
            detect_returns=[VisionType.TABLE],
            extract_return=vision_block,
        )

        result = parser.parse("test.pdf", input_meta)

        # 인자 file_meta(1)가 아니라 base_doc의 보강된 page_count(3)가 보존돼야 한다.
        assert result.file_meta.page_count == 3
