from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from common_schemas.enums import RiskLevel
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.ports.embedder_port import EmbedderPort
from nodes_graph.domain.ports.node_definition_repository import NodeDefinitionRepository


class InMemoryNodeDefinitionRepository(NodeDefinitionRepository):
    def __init__(self) -> None:
        self._store: dict[str, NodeDefinition] = {}

    async def upsert(self, definition: NodeDefinition) -> NodeDefinition:
        self._store[str(definition.node_id)] = definition
        return definition

    async def list_all(self, mvp_only: bool = False) -> list[NodeDefinition]:
        nodes = list(self._store.values())
        return [n for n in nodes if n.is_mvp] if mvp_only else nodes

    async def get_by_id(self, node_id: UUID) -> NodeDefinition | None:
        return self._store.get(str(node_id))

    async def search_by_embedding(self, query_embedding: list[float], limit: int = 10) -> list[NodeDefinition]:
        return list(self._store.values())[:limit]


class FakeEmbedder(EmbedderPort):
    async def embed(self, text: str) -> list[float]:
        return [0.1] * 768

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 768 for _ in texts]


def make_node_definition(**kwargs) -> NodeDefinition:
    defaults = dict(
        node_id=uuid4(),
        node_type="test_node",
        name="Test Node",
        category="테스트",
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="테스트 노드",
        is_mvp=True,
    )
    return NodeDefinition(**{**defaults, **kwargs})


@pytest.fixture
def node_repo() -> InMemoryNodeDefinitionRepository:
    return InMemoryNodeDefinitionRepository()


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()
