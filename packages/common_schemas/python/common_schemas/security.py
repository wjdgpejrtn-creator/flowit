from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# SSOT for user role values. auth `UserRole` re-exports this so `User.role`,
# `PermissionResolver.resolve(role=...)`, `PermissionSource.role`, and DB
# `users.role` CHECK constraint (`database/schemas/021`) share one symbol —
# adding a new role only requires editing this Literal.
UserRole = Literal["User", "team_manager", "company_manager", "Admin"]


class PermissionSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    role: UserRole
    department_id: UUID
    session_id: UUID
    current_workflow_id: Optional[UUID] = None
    current_skill_id: Optional[UUID] = None
    granted_scopes: list[Literal["Private", "Team", "Public"]]
    risk_ceiling: Literal["High", "Restricted"]


class PlaintextCredential(BaseModel):
    model_config = ConfigDict(frozen=False)

    credential_id: str
    credential_kind: Literal["fernet", "aes_gcm"]
    value: str

    def wipe(self) -> None:
        self.value = ""
