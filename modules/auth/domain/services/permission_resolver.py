from typing import Literal
from uuid import UUID

from common_schemas import PermissionSource


class PermissionResolver:
    def resolve(
        self,
        user_id: UUID,
        role: Literal["User", "Admin"],
        department_id: UUID,
        session_id: UUID,
    ) -> PermissionSource:
        if role == "Admin":
            risk_ceiling: Literal["High", "Restricted"] = "Restricted"
            granted_scopes: list[Literal["Private", "Team", "Public"]] = ["Private", "Team", "Public"]
        else:
            risk_ceiling = "High"
            granted_scopes = ["Private"]

        return PermissionSource(
            user_id=user_id,
            role=role,
            department_id=department_id,
            session_id=session_id,
            granted_scopes=granted_scopes,
            risk_ceiling=risk_ceiling,
        )
