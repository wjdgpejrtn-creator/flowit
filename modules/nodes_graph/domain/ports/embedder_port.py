from __future__ import annotations

from abc import ABC, abstractmethod


class EmbedderPort(ABC):
    """텍스트 → 벡터 임베딩 변환 인터페이스.

    구현체: BGE-M3 모델 (768차원) — ai_agent 모듈 담당.
    """

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """텍스트를 768차원 벡터로 변환."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """배치 임베딩. Plugin discovery 시 54종 노드 일괄 임베딩에 사용."""
        ...
