"""Plugin discovery 진입점 (`adapters/catalog/registry.py`) unit test.

5/14 plan §4.2 박아름 산출물 — 카탈로그 자동 등록 + UPSERT 흐름 검증.
"""
from __future__ import annotations

import pytest

from nodes_graph.adapters.catalog.registry import (
    discover_and_register,
    discover_node_definitions,
)


def test_discover_returns_full_catalog():
    nodes = discover_node_definitions()
    # 28 domain + 14 external (gemma_chat 추가, PR #68) + 14 toolset = 56
    assert len(nodes) == 56


def test_discover_returns_unique_node_ids():
    nodes = discover_node_definitions()
    ids = [n.node_id for n in nodes]
    assert len(ids) == len(set(ids))


def test_discover_returns_unique_node_types():
    nodes = discover_node_definitions()
    types = [n.node_type for n in nodes]
    assert len(types) == len(set(types))


@pytest.mark.asyncio
async def test_discover_and_register_registers_all_nodes(node_repo, embedder):
    count = await discover_and_register(node_repo, embedder)
    assert count == 56
    stored = await node_repo.list_all()
    assert len(stored) == 56


@pytest.mark.asyncio
async def test_discover_and_register_generates_embeddings(node_repo, embedder):
    """등록 후 모든 노드는 embedding이 채워져 있어야 함 (RegisterNodesUseCase가 자동 생성)."""
    await discover_and_register(node_repo, embedder)
    stored = await node_repo.list_all()
    for node in stored:
        assert node.embedding is not None
        assert len(node.embedding) == 768  # BGE-M3 차원


@pytest.mark.asyncio
async def test_discover_and_register_idempotent(node_repo, embedder):
    """두 번 호출해도 노드 수가 늘지 않음 (upsert idempotent)."""
    await discover_and_register(node_repo, embedder)
    await discover_and_register(node_repo, embedder)
    stored = await node_repo.list_all()
    assert len(stored) == 56
