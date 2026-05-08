"""
REQ-006 doc_parser — application/use_cases/extract_chunks.py

ExtractChunksUseCase
DocumentBlock → list[Chunk]

처리 흐름:
    DocumentBlock 입력
      → ChunkingService.chunk()
      → list[Chunk] 반환

Note:
    importance_score 는 REQ-004 AI_Agent 담당.
    이 유스케이스는 importance_score=None 인 상태로 반환.
"""
from __future__ import annotations

from common_schemas.document import DocumentBlock

from doc_parser.domain.entities.chunk import Chunk
from doc_parser.domain.services.chunking_service import ChunkingService


class ExtractChunksUseCase:
    """청크 추출 유스케이스.

    DocumentBlock 을 받아 Chunk 목록으로 분할.
    importance_score 는 REQ-004 AI_Agent 담당 — 여기선 None.

    Args:
        chunking_service: ChunkingService 인스턴스 (DI로 주입)
    """

    def __init__(self, chunking_service: ChunkingService) -> None:
        self._chunking_service = chunking_service

    def execute(
        self,
        document: DocumentBlock,
        strategy: str | None = None,
    ) -> list[Chunk]:
        """청크 추출 실행.

        Args:
            document: 파싱된 DocumentBlock (PII 마스킹 완료 상태)
            strategy: 청킹 전략 강제 지정 (선택)
                None     — 문서 구조에 따라 자동 선택
                "structural" | "page" | "token" | "table"

        Returns:
            list[Chunk]: 청킹 결과
                - importance_score=None (REQ-004 AI_Agent 가 채움)
        """
        return self._chunking_service.chunk(document, strategy=strategy)