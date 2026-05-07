from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class CheckpointModel(Base):
    __tablename__ = "checkpoints"

    thread_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(
        String(200), primary_key=True, server_default=""
    )
    checkpoint_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String(200))
    type: Mapped[str | None] = mapped_column(String(50))
    checkpoint: Mapped[dict] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, server_default="'{}'::jsonb"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CheckpointWriteModel(Base):
    __tablename__ = "checkpoint_writes"

    thread_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(
        String(200), primary_key=True, server_default=""
    )
    checkpoint_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(200))
    type: Mapped[str | None] = mapped_column(String(50))
    value: Mapped[dict | None] = mapped_column(JSONB)
