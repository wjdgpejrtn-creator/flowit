from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, uuid_pk


class DocumentModel(Base):
    __tablename__ = "documents"

    document_id: Mapped[uuid.UUID] = uuid_pk("document_id")
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    file_meta: Mapped[dict] = mapped_column(JSONB)
    parser_meta: Mapped[dict | None] = mapped_column(JSONB)
    blocks: Mapped[list] = mapped_column(JSONB, server_default="'[]'::jsonb")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list[DocumentChunkModel]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"

    chunk_id: Mapped[uuid.UUID] = uuid_pk("chunk_id")
    parent_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.document_id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    block_data: Mapped[dict] = mapped_column(JSONB)
    importance_score: Mapped[float | None] = mapped_column(Float)
    embedding = mapped_column(Vector(768), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[DocumentModel] = relationship(back_populates="chunks")
