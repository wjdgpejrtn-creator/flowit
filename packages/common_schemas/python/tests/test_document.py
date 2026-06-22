from uuid import uuid4

import pytest
from pydantic import ValidationError

from common_schemas.document import (
    AnalysisResult,
    BBox,
    Chunk,
    ChunkingStrategy,
    ContentBlock,
    DocumentBlock,
    FileMeta,
    ParseCoverage,
    ParserMeta,
    QualityGateResult,
    QualityMetrics,
    SheetMeta,
    SourceRef,
    WarningInfo,
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

    def test_new_fields_default(self):
        cb = ContentBlock(
            block_id=uuid4(),
            block_type="text",
            content="x",
        )
        assert cb.metadata is None
        assert cb.is_corrupted is False

    def test_metadata_and_is_corrupted(self):
        cb = ContentBlock(
            block_id=uuid4(),
            block_type="table",
            metadata={"data_rows": [], "normalized_headers": ["a", "b"]},
            is_corrupted=True,
        )
        assert cb.metadata["normalized_headers"] == ["a", "b"]
        assert cb.is_corrupted is True


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

    def test_coverage_counts_default(self):
        db = DocumentBlock(
            document_id=uuid4(),
            file_meta=FileMeta(
                file_name="x.pdf",
                file_type="pdf",
                mime_type="application/pdf",
                file_size=512,
            ),
            blocks=[],
        )
        assert db.vision_block_count == 0
        assert db.failed_block_count == 0

    def test_coverage_counts_set(self):
        db = DocumentBlock(
            document_id=uuid4(),
            file_meta=FileMeta(
                file_name="x.pdf",
                file_type="pdf",
                mime_type="application/pdf",
                file_size=512,
            ),
            blocks=[],
            vision_block_count=3,
            failed_block_count=1,
        )
        assert db.vision_block_count == 3
        assert db.failed_block_count == 1


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


def _metrics() -> QualityMetrics:
    return QualityMetrics(
        korean_ratio=0.9,
        broken_char_ratio=0.01,
        blocks_per_page=12.0,
        heading_ratio=0.1,
        valid_table_ratio=1.0,
        structural_chunk_ratio=0.8,
        total_chunks=20,
        avg_tokens=180.0,
    )


class TestWarningInfo:
    def test_create(self):
        w = WarningInfo(code="E0201", message="표 구조 불확실")
        assert w.code == "E0201"
        assert w.detail is None


class TestQualityMetrics:
    def test_create(self):
        assert _metrics().total_chunks == 20

    def test_frozen(self):
        m = _metrics()
        with pytest.raises(ValidationError):
            m.total_chunks = 1


class TestParseCoverage:
    def test_defaults(self):
        pc = ParseCoverage()
        assert pc.total_pages == 0
        assert pc.warnings == []

    def test_frozen(self):
        pc = ParseCoverage()
        with pytest.raises(ValidationError):
            pc.total_pages = 5


class TestQualityGateResult:
    def test_create(self):
        r = QualityGateResult(
            quality_status="success",
            metrics=_metrics(),
            warnings=[WarningInfo(code="E0201", message="x")],
            error_codes=[],
        )
        assert r.quality_status == "success"
        assert r.decision_reason is None
        assert r.coverage.total_pages == 0  # default_factory=ParseCoverage

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            QualityGateResult(
                quality_status="bogus",
                metrics=_metrics(),
                warnings=[],
                error_codes=[],
            )


class TestChunk:
    @staticmethod
    def _block() -> ContentBlock:
        return ContentBlock(block_id=uuid4(), block_type="text", content="x")

    def test_create_auto_id(self):
        c = Chunk(block=self._block(), chunk_index=0, parent_document_id=uuid4())
        assert c.chunk_id is not None
        assert c.token_count == 0
        assert c.chunk_type == "structural"
        assert c.importance_score is None
        assert c.embedding is None

    def test_mutable(self):
        # Chunk은 frozen 아님 — REQ-004 AI_Agent가 importance_score/embedding 후속 채움.
        c = Chunk(block=self._block(), chunk_index=0, parent_document_id=uuid4())
        c.importance_score = 0.7
        assert c.importance_score == 0.7


class TestChunkingStrategy:
    def test_create(self):
        s = ChunkingStrategy(max_tokens=512, overlap_tokens=64, token_estimator_mode="tiktoken")
        assert s.max_tokens == 512

    def test_frozen(self):
        s = ChunkingStrategy(max_tokens=512, overlap_tokens=64, token_estimator_mode="char_estimate")
        with pytest.raises(ValidationError):
            s.max_tokens = 1

    def test_invalid_estimator_mode(self):
        with pytest.raises(ValidationError):
            ChunkingStrategy(max_tokens=512, overlap_tokens=64, token_estimator_mode="bad")
