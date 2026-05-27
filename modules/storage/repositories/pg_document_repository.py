"""DocumentRepository 구현체 — `doc_parser.domain.ports.DocumentRepositoryPort` 상속.

`save` / `save_chunks` / `save_quality_log` 3 메서드를 PG ORM에 매핑한다.
모든 입력은 typed VO(`DocumentBlock` / `Chunk` / `QualityGateResult`) — JSONB 컬럼
저장 시점에 `.model_dump()`로 변환한다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from common_schemas import Chunk, DocumentBlock, QualityGateResult
from doc_parser.domain.ports.repository_port import DocumentRepositoryPort

from ..mappers.document_mapper import DocumentMapper
from ..orm.document_model import DocumentChunkModel, QualityLogModel


class PgDocumentRepository(DocumentRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, document: DocumentBlock) -> UUID:
        model = DocumentMapper.to_orm(document)
        self._session.add(model)
        await self._session.flush()
        return model.document_id

    async def save_chunks(self, chunks: list[Chunk]) -> None:
        for chunk in chunks:
            model = DocumentChunkModel(
                chunk_id=chunk.chunk_id,
                parent_document_id=chunk.parent_document_id,
                chunk_index=chunk.chunk_index,
                block_data=chunk.block.model_dump(mode="json"),
                importance_score=chunk.importance_score,
                embedding=chunk.embedding,
            )
            self._session.add(model)
        await self._session.flush()

    async def save_quality_log(self, result: QualityGateResult, document_id: UUID) -> None:
        model = QualityLogModel(
            log_id=uuid4(),
            document_id=document_id,
            quality_status=result.quality_status,
            metrics=result.metrics.model_dump(mode="json"),
            warnings=[w.model_dump(mode="json") for w in result.warnings],
            decision_reason=result.decision_reason or "",
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(model)
        await self._session.flush()
