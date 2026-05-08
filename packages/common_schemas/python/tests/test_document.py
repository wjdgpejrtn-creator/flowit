from uuid import uuid4

import pytest
from pydantic import ValidationError

from common_schemas.document import (
    AnalysisResult,
    BBox,
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParserMeta,
    SheetMeta,
    SourceRef,
)


class TestBBox:
    def test_create(self):
        bb = BBox(x1=0, y1=0, x2=100, y2=200)
        assert bb.x2 == 100

    def test_frozen(self):
        bb = BBox(x1=0, y1=0, x2=100, y2=200)
        with pytest.raises(ValidationError):
            bb.x1 = 5


class TestSheetMeta:
    def test_create(self):
        sm = SheetMeta(sheet_name="Sheet1", row_count=100, col_count=10)
        assert sm.sheet_name == "Sheet1"


class TestParserMeta:
    def test_create(self):
        pm = ParserMeta(parser_name="docling", parser_version="0.5.0")
        assert pm.parse_duration_ms is None


class TestSourceRef:
    def test_all_optional(self):
        sr = SourceRef()
        assert sr.page is None
        assert sr.section is None


class TestFileMeta:
    def test_required_fields(self):
        fm = FileMeta(
            file_name="test.pdf",
            file_type="pdf",
            mime_type="application/pdf",
            file_size=1024,
        )
        assert fm.page_count is None


class TestContentBlock:
    def test_text_block(self):
        cb = ContentBlock(
            block_id=uuid4(),
            block_type="text",
            content="Hello world",
        )
        assert cb.block_type == "text"

    def test_invalid_block_type(self):
        with pytest.raises(ValidationError):
            ContentBlock(
                block_id=uuid4(),
                block_type="invalid_type",
                content="x",
            )


class TestDocumentBlock:
    def test_create(self):
        db = DocumentBlock(
            document_id=uuid4(),
            file_meta=FileMeta(
                file_name="x.pdf",
                file_type="pdf",
                mime_type="application/pdf",
                file_size=512,
            ),
            blocks=[
                ContentBlock(
                    block_id=uuid4(),
                    block_type="heading",
                    content="Title",
                )
            ],
        )
        assert len(db.blocks) == 1


class TestAnalysisResult:
    def test_create(self):
        ar = AnalysisResult(
            document_title="Report",
            category="finance",
            summary="Summary text",
            key_points=["point1"],
            confidence=0.95,
            source_refs=[],
            warnings=[],
            questions=[],
            prompt_version="v1",
            template_type="general",
            few_shot_count=3,
        )
        assert ar.confidence == 0.95
