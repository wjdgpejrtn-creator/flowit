"""bootstrap.register_default_tools 단위 테스트."""
from __future__ import annotations

from uuid import NAMESPACE_DNS, uuid5

import pytest

from toolset.adapters.tool_registry_adapter import ToolRegistryAdapter

_EXPECTED_TOOL_NAMES = {
    "graphql",
    "rest_api",
    "webhook",
    "file_read",
    "file_transform",
    "file_write",
    "email_send",
    "slack_notify",
    "data_mapping",
    "json_transform",
    "text_template",
}


def _make_registry() -> ToolRegistryAdapter:
    from toolset.bootstrap import register_default_tools

    registry = ToolRegistryAdapter()
    register_default_tools(registry)
    return registry


class TestRegisterDefaultTools:
    def test_registers_exactly_11_tools(self):
        registry = _make_registry()
        assert len(registry) == 11

    def test_all_expected_tool_names_present(self):
        registry = _make_registry()
        registered = {m.name for m in registry.list_all()}
        assert registered == _EXPECTED_TOOL_NAMES

    def test_each_tool_retrievable_by_name(self):
        registry = _make_registry()
        for name in _EXPECTED_TOOL_NAMES:
            tool = registry.get(name)
            assert tool.name == name

    def test_uuids_are_deterministic(self):
        r1 = _make_registry()
        r2 = _make_registry()
        ids1 = {m.name: m.tool_id for m in r1.list_all()}
        ids2 = {m.name: m.tool_id for m in r2.list_all()}
        assert ids1 == ids2

    def test_uuids_match_expected_formula(self):
        registry = _make_registry()
        for meta in registry.list_all():
            expected = uuid5(NAMESPACE_DNS, f"toolset.{meta.name}")
            assert meta.tool_id == expected

    def test_calling_twice_does_not_raise(self):
        from toolset.bootstrap import register_default_tools

        registry = ToolRegistryAdapter()
        register_default_tools(registry)
        register_default_tools(registry)
        assert len(registry) == 11
