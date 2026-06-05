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
async def test_search_filters_non_executable_node_types():
    """실행 클래스 없는 node_type(예: 과거 게시 스킬이 남긴 도메인 NodeDef)은 후보에서
    제외된다 — drafter가 실행 불가 노드를 쓰면 실행 시 실패하기 때문(#378 그라운딩 가드)."""
    executable = _make_node_def(is_mvp=True, node_type="slack_post_message")
    polluted = _make_node_def(is_mvp=False, node_type="marketing_campaign_schedule")
    skill_node = _make_node_def(is_mvp=False, node_type="custom_itsm_skill")

    adapter = _make_adapter([executable, polluted, skill_node])
    results = await adapter.search("슬랙 알림 보내줘")

    node_types = [r.node_type for r in results]
    assert "slack_post_message" in node_types
    assert "marketing_campaign_schedule" not in node_types  # 실행 불가 → 필터
    assert "custom_itsm_skill" not in node_types  # 실행 불가 → 필터


@pytest.mark.asyncio
async def test_search_preserves_is_mvp_field():
    """검색 결과의 NodeConfig에 is_mvp 필드가 올바르게 전달되어야 한다(실행가능 노드 한정)."""
    mvp_node = _make_node_def(is_mvp=True, node_type="slack_post_message")
    non_mvp = _make_node_def(is_mvp=False, node_type="gmail_send")

    adapter = _make_adapter([mvp_node, non_mvp])
    results = await adapter.search("테스트 쿼리")

    result_map = {r.node_type: r for r in results}
    assert result_map["slack_post_message"].is_mvp is True
    assert result_map["gmail_send"].is_mvp is False


@pytest.mark.asyncio
async def test_search_calls_embedder_with_query():
    """검색 시 embedder가 올바른 쿼리로 호출되어야 한다."""
    adapter = _make_adapter([])
    await adapter.search("워크플로우 만들어줘", limit=5)

    adapter._embedder.embed.assert_called_once_with("워크플로우 만들어줘")


@pytest.mark.asyncio
async def test_search_overfetches_to_survive_filtering():
    """실행 불가 후보를 거른 뒤에도 limit을 채우도록 repo에서 over-fetch한다(#378)."""
    from ai_agent.adapters.node_registry_adapter import _OVERFETCH_FACTOR

    adapter = _make_adapter([])
    await adapter.search("테스트", limit=20)

    adapter._repo.search_by_embedding.assert_called_once()
    _, kwargs = adapter._repo.search_by_embedding.call_args
    assert kwargs.get("limit") == 20 * _OVERFETCH_FACTOR


@pytest.mark.asyncio
async def test_search_slices_to_limit_after_filter():
    """필터 후 결과가 limit으로 잘린다 (실행가능 후보가 limit 초과 시)."""
    nodes = [_make_node_def(is_mvp=True, node_type=nt) for nt in
             ("slack_post_message", "gmail_send", "anthropic_chat")]
    adapter = _make_adapter(nodes)
    results = await adapter.search("테스트", limit=2)
    assert len(results) == 2
