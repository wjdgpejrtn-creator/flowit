from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMPort(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict[str, Any]], tools: list[dict] | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...
