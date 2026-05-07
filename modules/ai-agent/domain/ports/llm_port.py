from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

T = TypeVar("T")


class LLMPort(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> str: ...

    @abstractmethod
    async def generate_structured(self, prompt: str, schema: type[T]) -> T: ...
