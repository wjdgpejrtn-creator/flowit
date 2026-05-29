from __future__ import annotations

from uuid import UUID

from ...domain.entities.node_definition import NodeDefinition
from ...domain.ports.embedder_port import EmbedderPort
from ...domain.ports.node_definition_repository import NodeDefinitionRepository


class SearchNodesUseCase:
    """벡터 임베딩 기반 노드 검색 유스케이스."""

    def __init__(self, node_def_repo: NodeDefinitionRepository, embedder: EmbedderPort) -> None:
        self._repo = node_def_repo
        self._embedder = embedder

    async def execute(
        self,
        query: str,
        limit: int = 10,
        viewer_user_id: UUID | None = None,
        viewer_team_ids: list[UUID] | None = None,
    ) -> list[NodeDefinition]:
        """
        1. embedder.embed(query) → query_embedding (768차원)
        2. node_def_repo.search_by_embedding(query_embedding, limit, scope)

        ADR-0020 (i): viewer scope 전달 시 가시 노드만 반환 (전역 + 본인 personal + 소속 team).
        """
        query_embedding = await self._embedder.embed(query)
        return await self._repo.search_by_embedding(
            query_embedding, limit, viewer_user_id=viewer_user_id, viewer_team_ids=viewer_team_ids
        )
