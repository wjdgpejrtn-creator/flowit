"""DocumentRepository 구현체 — `doc_parser.domain.ports.DocumentRepositoryPort` 상속.

`save` / `save_chunks` / `save_quality_log` / `get_by_id` / `list_by_owner` / `delete`를
PG ORM에 매핑한다. 모든 입력은 typed VO(`DocumentBlock` / `Chunk` / `QualityGateResult`) —
JSONB 컬럼 저장 시점에 `.model_dump()`로 변환한다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from common_schemas import Chunk, ContentBlock, DocumentBlock, QualityGateResult
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

    async def get_chunks(self, document_id: UUID) -> list[Chunk]:
        # SOP→스킬 추출(REQ-004 map-reduce/RAG)이 읽는 경로. block_data(JSONB)→ContentBlock 복원.
        # token_count/chunk_type 컬럼은 테이블에 없어 기본값(0/"structural")으로 복원된다 —
        # 호출자는 block.content 길이로 토큰을 추정해 배치한다.
        stmt = (
            select(DocumentChunkModel)
            .where(DocumentChunkModel.parent_document_id == document_id)
            .order_by(DocumentChunkModel.chunk_index)
        )
        result = await self._session.execute(stmt)
        return [
            Chunk(
                chunk_id=m.chunk_id,
                block=ContentBlock.model_validate(m.block_data),
                chunk_index=m.chunk_index,
                parent_document_id=m.parent_document_id,
                importance_score=m.importance_score,
                embedding=list(m.embedding) if m.embedding is not None else None,
            )
            for m in result.scalars().all()
        ]

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

    async def delete(self, document_id: UUID) -> bool:
        # hard delete — 자식(chunks/quality_log) 먼저 명시 제거 후 부모 삭제.
        # FK ON DELETE CASCADE가 있어도 DDL에 의존하지 않고 코드에서 보장(고아 방지).
        # GCS 원본 삭제는 라우터(api_server)가 object_storage로 수행 — Repo는 DB만 책임.
        model = await self._session.get(DocumentModel, document_id)
        if model is None:
            return False

        await self._session.execute(
            delete(DocumentChunkModel).where(
                DocumentChunkModel.parent_document_id == document_id
            )
        )
        await self._session.execute(
            delete(QualityLogModel).where(QualityLogModel.document_id == document_id)
        )
        await self._session.delete(model)
        await self._session.flush()
        return True
