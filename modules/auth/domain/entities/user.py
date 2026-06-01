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
    department_id: UUID | None = None  # authz/소유권 FK (departments). team scope 매칭에 사용.
    department: str | None = None  # 표시용 부서 라벨(users.department, 레거시 문자열). UI 배지 출력용.
    is_active: bool = True
    created_at: UtcDatetime
    updated_at: UtcDatetime
