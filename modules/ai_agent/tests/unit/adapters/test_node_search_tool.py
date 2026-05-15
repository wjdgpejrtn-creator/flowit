from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from common_schemas import NodeConfig
from common_schemas.enums import RiskLevel

from ai_agent.adapters.tools.node_search_tool import NodeSearchTool
from ai_agent.domain.ports.node_registry import NodeRegistry


def _make_node(node_type: str, name: str, desc: str = "") -> NodeConfig:
    return NodeConfig(
        node_id=uuid4(),
        node_type=node_type,
        name=name,
        category="api",
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description=desc or name,
        is_mvp=True,
    )


class TestNodeSearchTool:
    @pytest.mark.asyncio
    async def test_search_delegates_to_registry(self):
        registry = AsyncMock(spec=NodeRegistry)
        nodes = [_make_node("rest_api", "REST API")]
        registry.search.return_value = nodes

        tool = NodeSearchTool(registry)
        result = await tool.search("api 호출")

        registry.search.assert_called_once_with("api 호출", limit=10)
        assert result == nodes

    @pytest.mark.asyncio
    async def test_search_custom_limit(self):
        registry = AsyncMock(spec=NodeRegistry)
        registry.search.return_value = []

        tool = NodeSearchTool(registry)
        await tool.search("이메일", limit=3)

        registry.search.assert_called_once_with("이메일", limit=3)

    @pytest.mark.asyncio
    async def test_get_schema_delegates_to_registry(self):
        registry = AsyncMock(spec=NodeRegistry)
        node = _make_node("email_send", "이메일 발송")
        registry.get_schema.return_value = node

        tool = NodeSearchTool(registry)
        node_id = uuid4()
        result = await tool.get_schema(node_id)

        registry.get_schema.assert_called_once_with(node_id)
        assert result == node

    def test_format_for_prompt_empty(self):
        tool = NodeSearchTool(AsyncMock(spec=NodeRegistry))
        assert tool.format_for_prompt([]) == "(사용 가능한 노드 없음)"

    def test_format_for_prompt_single_node(self):
        tool = NodeSearchTool(AsyncMock(spec=NodeRegistry))
        node = _make_node("rest_api", "REST API", "HTTP 요청 실행")
        result = tool.format_for_prompt([node])
        assert "rest_api" in result
        assert "REST API" in result
        assert "HTTP 요청 실행" in result

    def test_format_for_prompt_multiple_nodes(self):
        tool = NodeSearchTool(AsyncMock(spec=NodeRegistry))
        nodes = [
            _make_node("rest_api", "REST API", "HTTP 호출"),
            _make_node("email_send", "이메일 발송", "SMTP 발송"),
        ]
        result = tool.format_for_prompt(nodes)
        lines = result.strip().splitlines()
        assert len(lines) == 2
        assert lines[0].startswith("- rest_api")
        assert lines[1].startswith("- email_send")
