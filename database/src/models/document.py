from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin


class DocumentModel(UUIDMixin, Base):
    __tablename__ = "documents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id")
    )
    filename: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    storage_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    metadata: Mapped[dict | None] = mapped_column(JSONB, server_default="'{}'::jsonb")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    blocks: Mapped[list[DocumentBlockModel]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentBlockModel(UUIDMixin, Base):
    __tablename__ = "document_blocks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    block_index: Mapped[int] = mapped_column(Integer)
    block_type: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(1024), nullable=True)
    metadata: Mapped[dict | None] = mapped_column(JSONB, server_default="'{}'::jsonb")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    document: Mapped[DocumentModel] = relationship(back_populates="blocks")
