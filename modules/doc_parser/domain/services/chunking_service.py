"""
REQ-006 doc_parser — domain/services/chunking_service.py

청킹 서비스
청킹 전략 우선순위:
    1순위: structural — heading 기준 섹션 분리
    2순위: page       — 페이지 단위 분리
    3순위: token      — 토큰 초과 시 재귀 분할
    4순위: table      — 표 독립 청크 (오버랩 없음)

토큰 계산:
    config/parser_quality.yaml 의 token_estimator_mode 키로 지정
    폐쇄망에서 tiktoken 사용 불가 시 char_estimate (char × 0.7) 로 전환
"""
from __future__ import annotations

from uuid import UUID, uuid4

from common_schemas.document import ContentBlock, DocumentBlock

from doc_parser.domain.entities.chunk import Chunk


class ChunkingService:
    """문서 청킹 서비스.

    DocumentBlock 을 받아 Chunk 목록으로 분할.
    청킹 전략은 문서 구조에 따라 자동 선택.

    Args:
        config: config/parser_quality.yaml 설정값
            - max_tokens: 청크 최대 토큰 수
            - token_chunk_overlap: 오버랩 토큰 수
            - token_estimator_mode: 토큰 계산 방식 (tiktoken | char_estimate)
    """

    def __init__(self, config: dict) -> None:
        self._max_tokens: int = config.get("max_tokens", 512)
        self._overlap_tokens: int = config.get("token_chunk_overlap", 50)
        self._estimator_mode: str = config.get("token_estimator_mode", "char_estimate")

    # ──────────────────────────────────────────
    # Public
    # ──────────────────────────────────────────

    def chunk(
        self,
        document: DocumentBlock,
        strategy: str | None = None,
    ) -> list[Chunk]:
        """DocumentBlock 을 Chunk 목록으로 분할.

        strategy 미지정 시 문서 구조에 따라 자동 선택:
            heading 블록 존재 → structural
            heading 없음      → page
            table 블록        → table (항상 독립 처리)

        Args:
            document: 파싱된 DocumentBlock
            strategy: 강제 지정할 청킹 전략 (선택)

        Returns:
            list[Chunk]: 청킹 결과
        """
        blocks = list(document.blocks)
        chunks: list[Chunk] = []
        chunk_index = 0

        # 표 블록은 항상 독립 청크로 먼저 분리
        table_blocks = [b for b in blocks if b.block_type == "table"]
        other_blocks = [b for b in blocks if b.block_type != "table"]

        for block in table_blocks:
            table_chunks = self._chunk_table(block, document.document_id, chunk_index)
            chunks.extend(table_chunks)
            chunk_index += len(table_chunks)

        if not other_blocks:
            return chunks

        # 전략 선택
        selected = strategy or self._select_strategy(other_blocks)

        if selected == "structural":
            new_chunks = self._chunk_by_section(other_blocks, document.document_id, chunk_index)
        elif selected == "page":
            new_chunks = self._chunk_by_page(other_blocks, document.document_id, chunk_index)
        elif selected == "token":
            new_chunks = self._chunk_by_token(other_blocks, document.document_id, chunk_index)
        else:
            new_chunks = self._chunk_by_page(other_blocks, document.document_id, chunk_index)

        chunks.extend(new_chunks)
        return chunks

    # ──────────────────────────────────────────
    # Private — 전략 선택
    # ──────────────────────────────────────────

    def _select_strategy(self, blocks: list[ContentBlock]) -> str:
        """문서 구조 기반 청킹 전략 자동 선택."""
        has_heading = any(b.block_type == "heading" for b in blocks)
        return "structural" if has_heading else "page"

    # ──────────────────────────────────────────
    # Private — 청킹 전략 구현
    # ──────────────────────────────────────────

    def _chunk_by_section(
        self,
        blocks: list[ContentBlock],
        document_id: UUID,
        start_index: int,
    ) -> list[Chunk]:
        """1순위: heading 기준 섹션 분리."""
        chunks: list[Chunk] = []
        current_section: list[ContentBlock] = []
        idx = start_index

        for block in blocks:
            if block.block_type == "heading" and current_section:
                new = self._finalize_section(current_section, document_id, idx)
                chunks.extend(new)
                idx += len(new)
                current_section = []
            current_section.append(block)

        if current_section:
            chunks.extend(self._finalize_section(current_section, document_id, idx))

        return chunks

    def _chunk_by_page(
        self,
        blocks: list[ContentBlock],
        document_id: UUID,
        start_index: int,
    ) -> list[Chunk]:
        """2순위: 페이지 단위 분리."""
        from itertools import groupby

        chunks: list[Chunk] = []
        idx = start_index
        keyfunc = lambda b: b.page or 0  # noqa: E731
        sorted_blocks = sorted(blocks, key=keyfunc)

        for _, group in groupby(sorted_blocks, key=keyfunc):
            page_blocks = list(group)
            new = self._finalize_section(page_blocks, document_id, idx)
            chunks.extend(new)
            idx += len(new)

        return chunks

    def _chunk_by_token(
        self,
        blocks: list[ContentBlock],
        document_id: UUID,
        start_index: int,
    ) -> list[Chunk]:
        """3순위: 토큰 최적화 재귀 분할."""
        chunks: list[Chunk] = []
        buffer_blocks: list[ContentBlock] = []
        idx = start_index

        for block in blocks:
            text = block.content or ""
            buffer_text = "\n".join(b.content or "" for b in buffer_blocks)
            if self._calc_token_count(buffer_text + text) > self._max_tokens and buffer_blocks:
                chunks.append(self._make_chunk(buffer_blocks, document_id, idx))
                idx += 1
                buffer_blocks = []
            buffer_blocks.append(block)

        if buffer_blocks:
            chunks.append(self._make_chunk(buffer_blocks, document_id, idx))

        return chunks

    def _chunk_table(
        self,
        block: ContentBlock,
        document_id: UUID,
        start_index: int,
    ) -> list[Chunk]:
        """4순위: 표 독립 청크 처리.

        XLSX 2층+3층 구조 분기:
            table[0]이 dict → normalized_headers + data_rows 로 재구성
            table[0]이 list → 기존 flat rows 처리

        20행 초과 시 header 유지 후 row group 단위로 분할.

        # TODO: ContentBlock.metadata 필드 추가 후 이 분기 제거 (황대원님 협의 필요)
        """
        if not block.table:
            return []

        # ── XLSX 2층+3층 구조 분기 ──
        if isinstance(block.table[0], dict):
            meta = block.table[0]
            normalized_headers = meta.get("normalized_headers", [])
            data_rows = meta.get("data_rows", [])
            # 청킹용 rows: normalized_headers 를 헤더 행으로 재구성
            rows = ([normalized_headers] + data_rows) if normalized_headers else data_rows
        else:
            # 기존 flat rows
            rows = block.table

        if not rows:
            return []

        data_rows_for_chunk = rows[1:]
        row_group_size = 20

        if len(data_rows_for_chunk) <= row_group_size:
            return [Chunk(
                chunk_id=uuid4(),
                block=block,
                chunk_index=start_index,
                parent_document_id=document_id,
            )]

        # 20행 초과 → header 유지하며 row group 단위 분할
        chunks: list[Chunk] = []
        header = rows[0] if rows else []
        for i, offset in enumerate(range(0, len(data_rows_for_chunk), row_group_size)):
            group_rows = [header] + data_rows_for_chunk[offset: offset + row_group_size]
            sub_block = block.model_copy(update={"table": group_rows})
            chunks.append(Chunk(
                chunk_id=uuid4(),
                block=sub_block,
                chunk_index=start_index + i,
                parent_document_id=document_id,
            ))

        return chunks

    # ──────────────────────────────────────────
    # Private — 유틸
    # ──────────────────────────────────────────

    def _calc_token_count(self, text: str) -> int:
        """토큰 수 계산."""
        if self._estimator_mode == "char_estimate":
            return int(len(text) * 0.7)
        try:
            import tiktoken  # noqa: PLC0415
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except ImportError:
            return int(len(text) * 0.7)

    def _finalize_section(
        self,
        blocks: list[ContentBlock],
        document_id: UUID,
        start_index: int,
    ) -> list[Chunk]:
        """섹션/페이지 블록을 청크로 변환.

        max_tokens 초과 시 token 분할로 재귀 처리.
        """
        if not blocks:
            return []

        text = "\n".join(b.content or "" for b in blocks).strip()
        if not text:
            return []

        if self._calc_token_count(text) <= self._max_tokens:
            return [self._make_chunk(blocks, document_id, start_index)]

        # 초과 시 token 분할
        return self._chunk_by_token(blocks, document_id, start_index)

    def _make_chunk(
        self,
        blocks: list[ContentBlock],
        document_id: UUID,
        chunk_index: int,
    ) -> Chunk:
        """Chunk 객체 생성 헬퍼.

        여러 블록을 하나의 청크로 묶을 때
        첫 번째 블록을 대표 block 으로 사용.
        """
        return Chunk(
            chunk_id=uuid4(),
            block=blocks[0],
            chunk_index=chunk_index,
            parent_document_id=document_id,
        )
