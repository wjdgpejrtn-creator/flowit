from __future__ import annotations

from uuid import UUID

from common_schemas import NodeConfig
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository

from ..domain.ports.node_registry import NodeRegistry


class NodeRegistryAdapter(NodeRegistry):
    """NodeRegistry 구현 — nodes_graph.NodeDefinitionRepository + EmbedderPort Facade.

    ai_agent는 NodeDefinitionRepository에 직접 의존하지 않고 이 어댑터를 통해서만 접근.
    검색 경로: query → BGE-M3 임베딩 → pgvector cosine similarity → NodeConfig 변환.
    """

    def __init__(
        self,
        repo: NodeDefinitionRepository,
        embedder: EmbedderPort,
    ) -> None:
        self._repo = repo
        self._embedder = embedder

    async def search(self, query: str, limit: int = 10) -> list[NodeConfig]:
        embedding = await self._embedder.embed(query)
        definitions = await self._repo.search_by_embedding(embedding, limit=limit)
        return [self._to_config(d) for d in definitions]

    async def get_schema(self, node_id: UUID) -> NodeConfig:
        definition = await self._repo.get_by_id(node_id)
        if definition is None:
            raise KeyError(f"NodeDefinition not found: {node_id}")
        return self._to_config(definition)

    @staticmethod
    def _to_config(d: NodeDefinition) -> NodeConfig:
        return NodeConfig(
            node_id=d.node_id,
            node_type=d.node_type,
            name=d.name,
            category=d.category,
            version=d.version,
            input_schema=d.input_schema,
            output_schema=d.output_schema,
            parameter_schema=d.parameter_schema,
            risk_level=d.risk_level,
            required_connections=d.required_connections,
            description=d.description,
            is_mvp=d.is_mvp,
        )
