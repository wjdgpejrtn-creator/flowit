from __future__ import annotations

from typing import Literal
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel


UserRole = Literal["User", "Admin"]


class User(BaseModel):
    user_id: UUID
    email: str
    name: str
    role: UserRole = "User"
    department_id: UUID | None = None
    is_active: bool = True
    created_at: UtcDatetime
    updated_at: UtcDatetime
