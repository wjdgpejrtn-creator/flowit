"""DocumentRepository 구현체.

Port ABC 위치: doc_parser.domain.ports.DocumentRepositoryPort (아직 미생성)
ABC 생성 시 상속 추가 예정.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from common_schemas import DocumentBlock

from ..mappers.document_mapper import DocumentMapper
from ..orm.document_model import ChunkModel, DocumentModel, QualityLogModel


class PgDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, document: DocumentBlock) -> UUID:
        model = DocumentMapper.to_orm(document)
        self._session.add(model)
        await self._session.flush()
        return model.document_id

    async def save_chunks(self, chunks: list[dict[str, Any]]) -> None:
        for chunk in chunks:
            model = ChunkModel(
                chunk_id=uuid4(),
                parent_document_id=chunk["parent_document_id"],
                chunk_index=chunk["chunk_index"],
                block_data=chunk.get("block_data", {}),
                importance_score=chunk.get("importance_score"),
                embedding=chunk.get("embedding"),
            )
            self._session.add(model)
        await self._session.flush()

    async def save_quality_log(self, result: dict[str, Any], document_id: UUID) -> None:
        model = QualityLogModel(
            log_id=uuid4(),
            document_id=document_id,
            quality_status=result.get("quality_status", "unknown"),
            metrics=result.get("metrics", {}),
            warnings=result.get("warnings", []),
            decision_reason=result.get("decision_reason", ""),
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(model)
        await self._session.flush()
