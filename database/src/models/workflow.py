from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from src.models.user import UserModel
    from src.models.execution import ExecutionModel


class WorkflowModel(TimestampMixin, Base):
    __tablename__ = "workflows"

    workflow_id: Mapped[uuid.UUID] = uuid_pk("workflow_id")
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id")
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(20), server_default="private")
    is_draft: Mapped[bool] = mapped_column(server_default="true")
    draft_spec: Mapped[dict | None] = mapped_column(JSONB)
    nodes: Mapped[dict] = mapped_column(JSONB, server_default="'[]'::jsonb")
    connections: Mapped[dict] = mapped_column(JSONB, server_default="'[]'::jsonb")
    created_via_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    sha256: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[UserModel] = relationship(back_populates="workflows")
    executions: Mapped[list[ExecutionModel]] = relationship(back_populates="workflow")
