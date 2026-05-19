from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common_schemas.enums import RiskLevel
from nodes_graph.domain.entities.node_definition import NodeDefinition

from ai_agent.adapters.node_registry_adapter import NodeRegistryAdapter


def _make_node_def(is_mvp: bool, node_type: str = "test_node") -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid4(),
        node_type=node_type,
        name=node_type,
        category="test",
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="test node",
        is_mvp=is_mvp,
    )


def _make_adapter(search_results: list[NodeDefinition]) -> NodeRegistryAdapter:
    repo = MagicMock()
    repo.search_by_embedding = AsyncMock(return_value=search_results)

    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 768)

    return NodeRegistryAdapter(repo=repo, embedder=embedder)


@pytest.mark.asyncio
async def test_search_includes_custom_skills():
    """커스텀 스킬(is_mvp=False)이 검색 결과에 포함되어야 한다."""
    mvp_node = _make_node_def(is_mvp=True, node_type="slack_post_message")
    custom_skill = _make_node_def(is_mvp=False, node_type="custom_itsm_skill")

    adapter = _make_adapter([mvp_node, custom_skill])
    results = await adapter.search("슬랙 알림 보내줘")

    node_types = [r.node_type for r in results]
    assert "slack_post_message" in node_types
    assert "custom_itsm_skill" in node_types


@pytest.mark.asyncio
async def test_search_preserves_is_mvp_field():
    """검색 결과의 NodeConfig에 is_mvp 필드가 올바르게 전달되어야 한다."""
    mvp_node = _make_node_def(is_mvp=True, node_type="mvp_node")
    custom_skill = _make_node_def(is_mvp=False, node_type="skill_node")

    adapter = _make_adapter([mvp_node, custom_skill])
    results = await adapter.search("테스트 쿼리")

    result_map = {r.node_type: r for r in results}
    assert result_map["mvp_node"].is_mvp is True
    assert result_map["skill_node"].is_mvp is False


@pytest.mark.asyncio
async def test_search_calls_embedder_with_query():
    """검색 시 embedder가 올바른 쿼리로 호출되어야 한다."""
    adapter = _make_adapter([])
    await adapter.search("워크플로우 만들어줘", limit=5)

    adapter._embedder.embed.assert_called_once_with("워크플로우 만들어줘")


@pytest.mark.asyncio
async def test_search_passes_limit_to_repo():
    """limit 파라미터가 repo.search_by_embedding에 전달되어야 한다."""
    adapter = _make_adapter([])
    await adapter.search("테스트", limit=20)

    adapter._repo.search_by_embedding.assert_called_once()
    _, kwargs = adapter._repo.search_by_embedding.call_args
    assert kwargs.get("limit") == 20
