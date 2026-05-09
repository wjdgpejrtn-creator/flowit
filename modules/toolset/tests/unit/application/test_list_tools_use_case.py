from __future__ import annotations

import pytest
from uuid import uuid4

from common_schemas.enums import RiskLevel

from toolset.adapters.tool_registry_adapter import ToolRegistryAdapter
from toolset.application.use_cases.list_tools_use_case import ListToolsUseCase
from toolset.tests.fixtures import DummyTool, HighRiskDummyTool, RestrictedDummyTool


@pytest.fixture
def registry_with_tools():
    reg = ToolRegistryAdapter()
    reg.register_tool(DummyTool(), tool_id=uuid4(), category="test")
    reg.register_tool(HighRiskDummyTool(), tool_id=uuid4(), category="test")
    reg.register_tool(RestrictedDummyTool(), tool_id=uuid4(), category="test")
    return reg


class TestListToolsUseCase:
    def test_list_all_tools(self, registry_with_tools):
        uc = ListToolsUseCase(registry_with_tools)
        result = uc.execute()
        assert len(result) == 3

    def test_filter_by_risk_level(self, registry_with_tools):
        uc = ListToolsUseCase(registry_with_tools)
        result = uc.execute(risk_level=RiskLevel.HIGH)
        assert len(result) == 1
        assert result[0].risk_level == RiskLevel.HIGH

    def test_filter_by_category(self, registry_with_tools):
        uc = ListToolsUseCase(registry_with_tools)
        result = uc.execute(category="test")
        assert len(result) == 3

    def test_empty_result_for_nonexistent_risk_level(self, registry_with_tools):
        uc = ListToolsUseCase(registry_with_tools)
        result = uc.execute(risk_level=RiskLevel.LOW)
        assert result == []

    def test_disabled_tool_excluded(self):
        from toolset.domain.entities.tool_metadata import ToolMetadata
        from unittest.mock import MagicMock
        from toolset.domain.ports.tool_registry import ToolRegistry

        disabled_meta = ToolMetadata.from_tool(DummyTool(), tool_id=uuid4(), category="test")
        object.__setattr__(disabled_meta, "is_enabled", False)

        registry = MagicMock(spec=ToolRegistry)
        registry.list_all.return_value = [disabled_meta]

        uc = ListToolsUseCase(registry)
        result = uc.execute()
        assert result == []
