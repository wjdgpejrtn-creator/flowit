import pytest
from uuid import uuid4

from common_schemas.enums import RiskLevel
from nodes_graph.application.use_cases.register_nodes_use_case import RegisterNodesUseCase
from nodes_graph.domain.entities.node_definition import NodeDefinition


class _Repo:
    def __init__(self):
        self._store = {}

    async def upsert(self, d): self._store[str(d.node_id)] = d; return d
    async def list_all(self, mvp_only=False): return list(self._store.values())
    async def get_by_id(self, nid): return self._store.get(str(nid))
    async def search_by_embedding(self, q, limit=10): return list(self._store.values())[:limit]


class _Embedder:
    async def embed(self, text): return [0.1] * 768
    async def embed_batch(self, texts): return [[0.1] * 768 for _ in texts]


def _def(node_type="test", embedding=None):
    return NodeDefinition(
        node_id=uuid4(), node_type=node_type, name=node_type, category="x", version="1.0.0",
        input_schema={}, output_schema={}, parameter_schema={},
        risk_level=RiskLevel.LOW, required_connections=[], description="x", is_mvp=True,
        embedding=embedding,
    )


@pytest.mark.asyncio
async def test_register_returns_count():
    repo = _Repo()
    nodes = [_def(f"node_{i}") for i in range(3)]
    count = await RegisterNodesUseCase(repo, _Embedder()).execute(nodes)
    assert count == 3


@pytest.mark.asyncio
async def test_register_generates_embedding_when_missing():
    repo = _Repo()
    node = _def(embedding=None)
    await RegisterNodesUseCase(repo, _Embedder()).execute([node])
    stored = await repo.get_by_id(node.node_id)
    assert stored.embedding is not None
    assert len(stored.embedding) == 768


@pytest.mark.asyncio
async def test_register_skips_embedding_when_present():
    repo = _Repo()
    existing = [0.5] * 768
    node = _def(embedding=existing)
    await RegisterNodesUseCase(repo, _Embedder()).execute([node])
    stored = await repo.get_by_id(node.node_id)
    assert stored.embedding == existing


@pytest.mark.asyncio
async def test_register_stores_nodes_in_repo():
    repo = _Repo()
    nodes = [_def("gmail_send"), _def("slack_post")]
    await RegisterNodesUseCase(repo, _Embedder()).execute(nodes)
    types = [n.node_type for n in await repo.list_all()]
    assert "gmail_send" in types
    assert "slack_post" in types
