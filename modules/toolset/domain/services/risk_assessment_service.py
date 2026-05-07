from __future__ import annotations

from common_schemas.exceptions import AuthorizationError
from common_schemas.security import PermissionSource

from ..entities.base_tool import BaseTool

_RISK_ORDER = ["Low", "Medium", "High", "Restricted"]


class RiskAssessmentService:
    """
    tool.risk_level이 permission_source.risk_ceiling을 초과하면 AuthorizationError.

    risk_ceiling은 Literal["High", "Restricted"] — str 타입.
    """

    def assess(self, tool: BaseTool, context: PermissionSource) -> bool:
        tool_idx = _RISK_ORDER.index(tool.risk_level.value)
        ceiling_idx = _RISK_ORDER.index(context.risk_ceiling)

        if tool_idx > ceiling_idx:
            raise AuthorizationError(
                message=(
                    f"Tool '{tool.name}' requires risk level '{tool.risk_level.value}', "
                    f"but user's ceiling is '{context.risk_ceiling}'."
                ),
                code="E_PERMISSION_DENIED",
            )
        return True
