from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingPort(ABC):
    """BGE-M3 텍스트 임베딩 Port (Modal llm-base endpoint)."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """텍스트를 임베딩 벡터로 변환."""
        ...
