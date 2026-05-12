from __future__ import annotations

import os
from typing import Any

import httpx

from nodes_graph.domain.ports.embedder_port import EmbedderPort

# BGE-M3 단일 문장 임베딩 기준 여유 있게 설정
_DEFAULT_TIMEOUT = 30.0


class ModalEmbeddingAdapter(EmbedderPort):
    """EmbedderPort 구현 — Modal llm-base app의 BGE-M3 임베딩 엔드포인트 호출.

    SSOT: nodes_graph.domain.ports.EmbedderPort (REQ-003 spec line 372-391,
    PR #30 머지 확정). ai_agent.EmbeddingPort는 폐기됨.

    엔드포인트 계약:
        POST {EMBEDDING_BASE_URL}/v1/embed
          req:  {"text": str}
          resp: {"embedding": list[float]}  # 768차원

        POST {EMBEDDING_BASE_URL}/v1/embed_batch
          req:  {"texts": list[str]}
          resp: {"embeddings": list[list[float]]}
    """

    def __init__(self, base_url: str | None = None) -> None:
        url = base_url or os.getenv("EMBEDDING_BASE_URL")
        if not url:
            raise ValueError("EMBEDDING_BASE_URL 환경 변수가 설정되지 않았습니다.")
        self._base_url = url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def embed(self, text: str) -> list[float]:
        response = await self._client.post(
            f"{self._base_url}/v1/embed",
            json={"text": text},
        )
        response.raise_for_status()
        return response.json()["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.post(
            f"{self._base_url}/v1/embed_batch",
            json={"texts": texts},
        )
        response.raise_for_status()
        return response.json()["embeddings"]

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ModalEmbeddingAdapter:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
