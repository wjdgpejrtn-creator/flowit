from __future__ import annotations

from ...domain.entities.node_definition import NodeDefinition
from ...domain.ports.embedder_port import EmbedderPort
from ...domain.ports.node_definition_repository import NodeDefinitionRepository


class SearchNodesUseCase:
    """벡터 임베딩 기반 노드 검색 유스케이스."""

    def __init__(self, node_def_repo: NodeDefinitionRepository, embedder: EmbedderPort) -> None:
        self._repo = node_def_repo
        self._embedder = embedder

    async def execute(self, query: str, limit: int = 10) -> list[NodeDefinition]:
        """
        1. embedder.embed(query) → query_embedding (768차원)
        2. node_def_repo.search_by_embedding(query_embedding, limit)
        """
        query_embedding = await self._embedder.embed(query)
        return await self._repo.search_by_embedding(query_embedding, limit)
