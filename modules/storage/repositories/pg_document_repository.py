"""DocumentRepository 구현체 — `doc_parser.domain.ports.DocumentRepositoryPort` 상속.

`save` / `save_chunks` / `save_quality_log` 3 메서드를 PG ORM에 매핑한다.
모든 입력은 typed VO(`DocumentBlock` / `Chunk` / `QualityGateResult`) — JSONB 컬럼
저장 시점에 `.model_dump()`로 변환한다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common_schemas import Chunk, DocumentBlock, QualityGateResult
from doc_parser.domain.ports.repository_port import DocumentRepositoryPort

from ..mappers.document_mapper import DocumentMapper
from ..orm.document_model import DocumentChunkModel, DocumentModel, QualityLogModel


class PgDocumentRepository(DocumentRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, document: DocumentBlock) -> UUID:
        # upload → analyze 사이 UPSERT 지원. upload 시 빈 blocks=[]로 INSERT,
        # analyze 완료 후 동일 document_id로 parsed blocks 채워 재호출 시 UPDATE.
        # session.add는 INSERT-only라 두 번째 호출 시 PK 충돌 — merge가 정확한 의미.
        merged = await self._session.merge(DocumentMapper.to_orm(document))
        await self._session.flush()
        return merged.document_id

    async def get_by_id(self, document_id: UUID) -> DocumentBlock | None:
        model = await self._session.get(DocumentModel, document_id)
        return DocumentMapper.to_domain(model) if model is not None else None

    async def list_by_owner(self, user_id: UUID) -> list[DocumentBlock]:
        stmt = (
            select(DocumentModel)
            .where(DocumentModel.user_id == user_id)
            .order_by(DocumentModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [DocumentMapper.to_domain(m) for m in result.scalars().all()]

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
