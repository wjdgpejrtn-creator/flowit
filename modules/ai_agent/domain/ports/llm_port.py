from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMPort(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> str: ...

    @abstractmethod
    async def generate_structured(
        self, prompt: str, schema: type[T], max_tokens: int | None = None
    ) -> T:
        """structured(JSON) 생성. max_tokens는 출력 토큰 예산(생략 시 구현체 기본값).

        장문 출력이 필요한 호출부(SOP 추출 등)는 명시적으로 상향하고, 워크플로우
        초안처럼 입력이 크고 출력이 작은 경로는 기본값(작은 예산)으로 입력 여유를 확보한다.
        """
        ...
