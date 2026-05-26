from __future__ import annotations

from uuid import UUID

from common_schemas import UserRole
from common_schemas.types import UtcDatetime
from pydantic import BaseModel

# Re-export so existing imports `from auth.domain.entities.user import UserRole` keep working.
# SSOT is `common_schemas.UserRole` — see security.py docstring (PR #157 review ①).
__all__ = ["User", "UserRole"]


class User(BaseModel):
    user_id: UUID
    email: str
    name: str
    role: UserRole = "User"
    department_id: UUID | None = None
    is_active: bool = True
    created_at: UtcDatetime
    updated_at: UtcDatetime
