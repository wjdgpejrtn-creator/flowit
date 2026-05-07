"""Vector search (HNSW cosine similarity) integration tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.models.node_definition import NodeDefinitionModel
from src.repositories.node_definition_repository import NodeDefinitionRepository


def _random_embedding(dim: int = 1024) -> list[float]:
    """Generate a normalized random embedding vector."""
    import random
    vec = [random.gauss(0, 1) for _ in range(dim)]
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


@pytest.mark.asyncio
async def test_vector_search_returns_results(db_session):
    repo = NodeDefinitionRepository(db_session)

    emb1 = _random_embedding()
    emb2 = _random_embedding()

    await repo.upsert(
        node_type="test_node_a",
        category="action",
        display_name="Test Node A",
        embedding=emb1,
    )
    await repo.upsert(
        node_type="test_node_b",
        category="trigger",
        display_name="Test Node B",
        embedding=emb2,
    )

    results = await repo.search_by_embedding(emb1, top_k=5)
    assert len(results) >= 1
    assert results[0].node_type == "test_node_a"


@pytest.mark.asyncio
async def test_reembed_updates_vector(db_session):
    repo = NodeDefinitionRepository(db_session)

    old_emb = _random_embedding()
    await repo.upsert(
        node_type="reembed_test",
        category="utility",
        display_name="Reembed Test",
        embedding=old_emb,
    )

    from sqlalchemy import select
    from src.models.node_definition import NodeDefinitionModel

    stmt = select(NodeDefinitionModel).where(
        NodeDefinitionModel.node_type == "reembed_test"
    )
    result = await db_session.execute(stmt)
    node = result.scalars().first()

    new_emb = _random_embedding()
    await repo.reembed(node.id, new_emb)
    await db_session.refresh(node)

    assert list(node.embedding) != old_emb
