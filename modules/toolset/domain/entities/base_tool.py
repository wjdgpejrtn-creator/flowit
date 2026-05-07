from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from common_schemas.enums import RiskLevel


class BaseTool(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    @abstractmethod
    def risk_level(self) -> RiskLevel: ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]: ...

    @property
    @abstractmethod
    def output_schema(self) -> dict[str, Any]: ...

    @abstractmethod
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]: ...
