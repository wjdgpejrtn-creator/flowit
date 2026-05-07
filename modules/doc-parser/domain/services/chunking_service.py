"""
REQ-006 doc-parser — domain/services/chunking_service.py

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

from uuid import uuid4

from common_schemas.document import ContentBlock, DocumentBlock, SourceRef

from doc_parser.domain.entities.chunk import Chunk, ChunkOverlapMeta


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
                "structural" | "page" | "token" | "table"

        Returns:
            list[Chunk]: 청킹 결과
        """
        blocks = list(document.blocks)
        chunks: list[Chunk] = []

        # 표 블록은 항상 독립 청크로 먼저 분리
        table_blocks = [b for b in blocks if b.block_type == "table"]
        other_blocks = [b for b in blocks if b.block_type != "table"]

        for block in table_blocks:
            chunks.extend(self._chunk_table(block))

        if not other_blocks:
            return chunks

        # 전략 선택
        selected = strategy or self._select_strategy(other_blocks)

        if selected == "structural":
            chunks.extend(self._chunk_by_section(other_blocks))
        elif selected == "page":
            chunks.extend(self._chunk_by_page(other_blocks))
        elif selected == "token":
            chunks.extend(self._chunk_by_token(other_blocks))
        else:
            chunks.extend(self._chunk_by_page(other_blocks))

        # 오버랩 적용 (table 제외)
        non_table = [c for c in chunks if c.chunk_type != "table"]
        table_chunks = [c for c in chunks if c.chunk_type == "table"]
        overlapped = self._apply_overlap(non_table)

        return overlapped + table_chunks

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

    def _chunk_by_section(self, blocks: list[ContentBlock]) -> list[Chunk]:
        """1순위: heading 기준 섹션 분리.

        heading 블록을 기준으로 섹션을 나누고,
        섹션이 max_tokens 초과 시 token 분할로 재귀 처리.
        """
        chunks: list[Chunk] = []
        current_section: list[ContentBlock] = []

        for block in blocks:
            if block.block_type == "heading" and current_section:
                chunks.extend(self._finalize_section(current_section, "structural"))
                current_section = []
            current_section.append(block)

        if current_section:
            chunks.extend(self._finalize_section(current_section, "structural"))

        return chunks

    def _chunk_by_page(self, blocks: list[ContentBlock]) -> list[Chunk]:
        """2순위: 페이지 단위 분리.

        같은 page 번호의 블록을 묶어 하나의 청크로.
        페이지가 max_tokens 초과 시 token 분할로 재귀 처리.
        """
        from itertools import groupby

        chunks: list[Chunk] = []
        keyfunc = lambda b: b.page or 0  # noqa: E731
        sorted_blocks = sorted(blocks, key=keyfunc)

        for _, group in groupby(sorted_blocks, key=keyfunc):
            page_blocks = list(group)
            chunks.extend(self._finalize_section(page_blocks, "page"))

        return chunks

    def _chunk_by_token(self, blocks: list[ContentBlock]) -> list[Chunk]:
        """3순위: 토큰 최적화 재귀 분할.

        paragraph / list 블록만 대상.
        max_tokens 초과 시 재귀적으로 분할.
        """
        chunks: list[Chunk] = []
        buffer = ""
        buffer_blocks: list[ContentBlock] = []

        for block in blocks:
            text = block.content or ""
            if self._calc_token_count(buffer + text) > self._max_tokens and buffer:
                chunks.append(self._make_chunk(buffer, buffer_blocks, "token"))
                buffer = ""
                buffer_blocks = []
            buffer += text + "\n"
            buffer_blocks.append(block)

        if buffer:
            chunks.append(self._make_chunk(buffer.strip(), buffer_blocks, "token"))

        return chunks

    def _chunk_table(self, block: ContentBlock) -> list[Chunk]:
        """4순위: 표 독립 청크 처리.

        표는 항상 독립 청크.
        오버랩 없음.
        20행 초과 시 header 유지 후 row group 단위로 분할.
        """
        if not block.table:
            return []

        rows = block.table
        header = rows[0] if rows else []
        data_rows = rows[1:]
        row_group_size = 20

        if len(data_rows) <= row_group_size:
            content = self._table_to_text(rows)
            return [self._make_chunk(content, [block], "table")]

        # 20행 초과 → header 유지 후 분할
        chunks: list[Chunk] = []
        for i in range(0, len(data_rows), row_group_size):
            group = [header] + data_rows[i: i + row_group_size]
            content = self._table_to_text(group)
            chunks.append(self._make_chunk(content, [block], "table"))

        return chunks

    def _apply_overlap(self, chunks: list[Chunk]) -> list[Chunk]:
        """인접 청크 간 오버랩 적용 (table 제외).

        overlap_tokens 만큼 이전 청크 끝 텍스트를 다음 청크 앞에 추가.
        """
        if len(chunks) <= 1:
            return chunks

        result: list[Chunk] = [chunks[0]]

        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            curr = chunks[i]

            overlap_text = self._get_overlap_text(prev.content)
            if not overlap_text:
                result.append(curr)
                continue

            new_content = overlap_text + "\n" + curr.content
            new_token_count = self._calc_token_count(new_content)
            overlap_meta = ChunkOverlapMeta(
                has_overlap=True,
                overlap_tokens=self._calc_token_count(overlap_text),
            )
            result.append(
                curr.model_copy(
                    update={
                        "content": new_content,
                        "token_count": new_token_count,
                        "overlap_meta": overlap_meta,
                    }
                )
            )

        return result

    # ──────────────────────────────────────────
    # Private — 유틸
    # ──────────────────────────────────────────

    def _calc_token_count(self, text: str) -> int:
        """토큰 수 계산.

        token_estimator_mode:
            char_estimate — char × 0.7 (폐쇄망 기본값)
            tiktoken      — tiktoken 라이브러리 사용 (외부망)
        """
        if self._estimator_mode == "char_estimate":
            return int(len(text) * 0.7)

        # tiktoken 모드 (Phase 2 — 폐쇄망 미지원)
        try:
            import tiktoken  # noqa: PLC0415
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except ImportError:
            return int(len(text) * 0.7)

    def _finalize_section(
        self,
        blocks: list[ContentBlock],
        chunk_type: str,
    ) -> list[Chunk]:
        """섹션/페이지 블록을 청크로 변환.

        max_tokens 초과 시 token 분할로 재귀 처리.
        """
        text = "\n".join(b.content or "" for b in blocks).strip()
        if not text:
            return []

        if self._calc_token_count(text) <= self._max_tokens:
            return [self._make_chunk(text, blocks, chunk_type)]

        # 초과 시 token 분할
        return self._chunk_by_token(blocks)

    def _make_chunk(
        self,
        content: str,
        blocks: list[ContentBlock],
        chunk_type: str,
    ) -> Chunk:
        """Chunk 객체 생성 헬퍼."""
        source_ref = blocks[0].source_ref if blocks and blocks[0].source_ref else SourceRef()
        return Chunk(
            chunk_id=uuid4(),
            chunk_type=chunk_type,  # type: ignore[arg-type]
            content=content.strip(),
            token_count=self._calc_token_count(content),
            source_ref=source_ref,
            block_ids=[b.block_id for b in blocks],
        )

    def _get_overlap_text(self, text: str) -> str:
        """이전 청크에서 오버랩할 텍스트 추출 (끝부분)."""
        words = text.split()
        overlap_word_count = max(1, self._overlap_tokens // 2)
        if len(words) <= overlap_word_count:
            return ""
        return " ".join(words[-overlap_word_count:])

    def _table_to_text(self, rows: list[list]) -> str:
        """표 데이터를 텍스트로 변환."""
        return "\n".join("\t".join(str(cell) for cell in row) for row in rows)