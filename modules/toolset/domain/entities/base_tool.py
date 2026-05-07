from __future__ import annotations

from abc import ABC, abstractmethod

from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential


class BaseTool(ABC):
    tool_id: str
    name: str
    description: str
    risk_level: RiskLevel
    input_schema: dict
    output_schema: dict

    @abstractmethod
    async def run(
        self,
        params: dict,
        credential: PlaintextCredential | None,
    ) -> dict: ...

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        required = ("tool_id", "name", "description", "risk_level", "input_schema", "output_schema")
        if not getattr(cls, "__abstractmethods__", None):
            missing = [attr for attr in required if not hasattr(cls, attr)]
            if missing:
                raise TypeError(f"{cls.__name__} must define class variables: {missing}")
