from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from src.models.workflow import WorkflowModel


class DepartmentModel(Base):
    __tablename__ = "departments"

    department_id: Mapped[uuid.UUID] = uuid_pk("department_id")
    name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list[UserModel]] = relationship(back_populates="department_rel")


class UserModel(TimestampMixin, Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = uuid_pk("user_id")
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), server_default="User")
    department: Mapped[str | None] = mapped_column(String(100))
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.department_id")
    )
    is_active: Mapped[bool] = mapped_column(server_default="true")

    department_rel: Mapped[DepartmentModel | None] = relationship(
        back_populates="users"
    )
    workflows: Mapped[list[WorkflowModel]] = relationship(back_populates="user")
