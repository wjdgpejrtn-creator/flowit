"""
REQ-006 doc_parser — tests/unit/domain/test_chunking_service.py

ChunkingService 유닛 테스트

검증 항목:
    - XLSX 병합셀 구조 (block.metadata 기반 분기)
    - 기존 flat rows 처리
    - 20행 초과 분할
    - 전략 자동 선택 (structural / page)
    - 표 블록 독립 청크 처리
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from common_schemas.document import ContentBlock, DocumentBlock, FileMeta, ParserMeta, SourceRef

from doc_parser.domain.services.chunking_service import ChunkingService


# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────

_DEFAULT_CONFIG = {
    "max_tokens": 512,
    "token_chunk_overlap": 50,
    "token_estimator_mode": "char_estimate",
}


def _make_service(config: dict | None = None) -> ChunkingService:
    return ChunkingService(config or _DEFAULT_CONFIG)


def _make_document(blocks: list[ContentBlock]) -> DocumentBlock:
    return DocumentBlock(
        document_id=uuid4(),
        file_meta=FileMeta(
            file_name="test.xlsx",
            file_type="xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            file_size=1024,
        ),
        parser=ParserMeta(parser_name="XlsxParser", parser_version="1.0.0"),
        blocks=blocks,
    )


def _make_flat_table_block(rows: list[list[str]], page: int = 1) -> ContentBlock:
    """병합셀 없는 flat rows 표 블록."""
    return ContentBlock(
        block_id=uuid4(),
        block_type="table",
        content=None,
        page=page,
        table=rows,
        source_ref=SourceRef(page=page, block_index=0),
    )


def _make_metadata_table_block(
    normalized_headers: list[str],
    data_rows: list[list[str]],
    page: int = 1,
) -> ContentBlock:
    """XLSX 병합셀 구조 — metadata 기반 표 블록."""
    raw_grid = [normalized_headers] + data_rows
    return ContentBlock(
        block_id=uuid4(),
        block_type="table",
        content=None,
        page=page,
        table=data_rows,   # flat rows (청킹용)
        metadata={
            "raw_grid": raw_grid,
            "normalized_headers": normalized_headers,
            "merged_cells": [{"range": "B1:C1", "value": "주문"}],
            "data_rows": data_rows,
            "has_charts": False,
            "has_images": False,
        },
        source_ref=SourceRef(page=page, block_index=0),
    )


def _make_text_block(content: str = "본문 텍스트", page: int = 1) -> ContentBlock:
    return ContentBlock(
        block_id=uuid4(),
        block_type="text",
        content=content,
        page=page,
        source_ref=SourceRef(page=page, block_index=0),
    )


def _make_heading_block(content: str = "섹션 제목", page: int = 1) -> ContentBlock:
    return ContentBlock(
        block_id=uuid4(),
        block_type="heading",
        content=content,
        page=page,
        source_ref=SourceRef(page=page, block_index=0),
    )


# ──────────────────────────────────────────
# XLSX metadata 분기 테스트
# ──────────────────────────────────────────

class TestChunkTableMetadata:

    def test_metadata_기반_표블록_청킹(self):
        """block.metadata 있는 XLSX 병합셀 블록 → 정상 청킹."""
        headers = ["카테고리", "주문_주문수", "주문_매출"]
        data_rows = [
            ["의류", "100", "500000"],
            ["가전", "50", "3000000"],
        ]
        block = _make_metadata_table_block(headers, data_rows)
        doc = _make_document([block])

        service = _make_service()
        chunks = service.chunk(doc)

        assert len(chunks) == 1
        assert chunks[0].block.block_id == block.block_id

    def test_metadata_없는_flat_rows_청킹(self):
        """block.metadata 없는 flat rows 블록 → 기존 방식으로 청킹."""
        rows = [
            ["헤더1", "헤더2", "헤더3"],
            ["값1", "값2", "값3"],
            ["값4", "값5", "값6"],
        ]
        block = _make_flat_table_block(rows)
        doc = _make_document([block])

        service = _make_service()
        chunks = service.chunk(doc)

        assert len(chunks) == 1
        assert chunks[0].block.block_id == block.block_id

    def test_metadata_normalized_headers_청킹용_rows_구성(self):
        """metadata 있을 때 normalized_headers + data_rows 로 청킹용 rows 구성."""
        headers = ["카테고리", "주문_주문수", "주문_매출"]
        data_rows = [["의류", "100", "500000"]]
        block = _make_metadata_table_block(headers, data_rows)
        doc = _make_document([block])

        service = _make_service()
        chunks = service.chunk(doc)

        # 청킹 결과에 블록이 포함돼야 함
        assert len(chunks) == 1

    def test_metadata_data_rows_없을때_빈청크(self):
        """metadata에 data_rows가 비어있으면 청크 없음."""
        block = _make_metadata_table_block(
            normalized_headers=["헤더1", "헤더2"],
            data_rows=[],
        )
        # table도 비워서 rows 없는 상태
        block = block.model_copy(update={"table": []})
        doc = _make_document([block])

        service = _make_service()
        chunks = service.chunk(doc)

        assert len(chunks) == 0

    def test_metadata_normalized_headers_없을때_data_rows만_사용(self):
        """metadata에 normalized_headers 없으면 data_rows만으로 청킹."""
        data_rows = [["값1", "값2"], ["값3", "값4"]]
        block = ContentBlock(
            block_id=uuid4(),
            block_type="table",
            content=None,
            page=1,
            table=data_rows,
            metadata={
                "raw_grid": data_rows,
                "normalized_headers": [],   # 빈 헤더
                "merged_cells": [],
                "data_rows": data_rows,
                "has_charts": False,
                "has_images": False,
            },
            source_ref=SourceRef(page=1, block_index=0),
        )
        doc = _make_document([block])

        service = _make_service()
        chunks = service.chunk(doc)

        assert len(chunks) == 1


# ──────────────────────────────────────────
# 20행 초과 분할 테스트
# ──────────────────────────────────────────

class TestChunkTableSplit:

    def test_20행_이하_단일청크(self):
        """데이터 행 20개 이하 → 청크 1개."""
        rows = [["헤더1", "헤더2"]] + [[f"값{i}A", f"값{i}B"] for i in range(20)]
        block = _make_flat_table_block(rows)
        doc = _make_document([block])

        service = _make_service()
        chunks = service.chunk(doc)

        assert len(chunks) == 1

    def test_21행_2청크로_분할(self):
        """데이터 행 21개 → 청크 2개 (20 + 1)."""
        rows = [["헤더1", "헤더2"]] + [[f"값{i}A", f"값{i}B"] for i in range(21)]
        block = _make_flat_table_block(rows)
        doc = _make_document([block])

        service = _make_service()
        chunks = service.chunk(doc)

        assert len(chunks) == 2

    def test_40행_2청크로_분할(self):
        """데이터 행 40개 → 청크 2개 (20 + 20)."""
        rows = [["헤더1", "헤더2"]] + [[f"값{i}A", f"값{i}B"] for i in range(40)]
        block = _make_flat_table_block(rows)
        doc = _make_document([block])

        service = _make_service()
        chunks = service.chunk(doc)

        assert len(chunks) == 2

    def test_41행_3청크로_분할(self):
        """데이터 행 41개 → 청크 3개 (20 + 20 + 1)."""
        rows = [["헤더1", "헤더2"]] + [[f"값{i}A", f"값{i}B"] for i in range(41)]
        block = _make_flat_table_block(rows)
        doc = _make_document([block])

        service = _make_service()
        chunks = service.chunk(doc)

        assert len(chunks) == 3

    def test_metadata_21행_분할(self):
        """metadata 기반 블록도 21행 초과 시 분할."""
        headers = ["카테고리", "주문수"]
        data_rows = [[f"카테고리{i}", str(i * 100)] for i in range(21)]
        block = _make_metadata_table_block(headers, data_rows)
        doc = _make_document([block])

        service = _make_service()
        chunks = service.chunk(doc)

        assert len(chunks) == 2

    def test_chunk_index_연속성(self):
        """분할된 청크의 chunk_index가 연속적."""
        rows = [["헤더1", "헤더2"]] + [[f"값{i}A", f"값{i}B"] for i in range(41)]
        block = _make_flat_table_block(rows)
        doc = _make_document([block])

        service = _make_service()
        chunks = service.chunk(doc)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i


# ──────────────────────────────────────────
# 전략 선택 테스트
# ──────────────────────────────────────────

class TestStrategySelection:

    def test_heading_있으면_structural(self):
        """heading 블록 있으면 structural 전략 선택."""
        blocks = [
            _make_heading_block("섹션1"),
            _make_text_block("내용1"),
        ]
        doc = _make_document(blocks)

        service = _make_service()
        chunks = service.chunk(doc)

        assert len(chunks) >= 1
        assert all(c.chunk_type == "structural" for c in chunks)

    def test_heading_없으면_page(self):
        """heading 없으면 page 전략 선택."""
        blocks = [
            _make_text_block("내용1", page=1),
            _make_text_block("내용2", page=2),
        ]
        doc = _make_document(blocks)

        service = _make_service()
        chunks = service.chunk(doc)

        assert len(chunks) >= 1

    def test_표블록_항상_독립청크(self):
        """표 블록은 전략 무관하게 항상 독립 청크."""
        blocks = [
            _make_heading_block("섹션1"),
            _make_text_block("내용"),
            _make_flat_table_block([["헤더"], ["값"]]),
        ]
        doc = _make_document(blocks)

        service = _make_service()
        chunks = service.chunk(doc)

        # 표 청크가 1개 이상 포함돼야 함
        table_chunks = [c for c in chunks if c.block.block_type == "table"]
        assert len(table_chunks) >= 1

    def test_parent_document_id_일치(self):
        """모든 청크의 parent_document_id가 document_id와 일치."""
        blocks = [_make_text_block(), _make_flat_table_block([["헤더"], ["값"]])]
        doc = _make_document(blocks)

        service = _make_service()
        chunks = service.chunk(doc)

        for chunk in chunks:
            assert chunk.parent_document_id == doc.document_id

    def test_importance_score_none(self):
        """importance_score는 항상 None — REQ-004 담당."""
        blocks = [_make_text_block()]
        doc = _make_document(blocks)

        service = _make_service()
        chunks = service.chunk(doc)

        for chunk in chunks:
            assert chunk.importance_score is None

    def test_embedding_none(self):
        """embedding은 항상 None — REQ-004 담당."""
        blocks = [_make_text_block()]
        doc = _make_document(blocks)

        service = _make_service()
        chunks = service.chunk(doc)

        for chunk in chunks:
            assert chunk.embedding is None
