from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PermissionSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    role: Literal["User", "Admin"]
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
