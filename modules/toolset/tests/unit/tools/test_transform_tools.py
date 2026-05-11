from __future__ import annotations

import pytest

from toolset.adapters.tools.transform.data_mapping_tool import DataMappingTool
from toolset.adapters.tools.transform.json_transform_tool import JsonTransformTool
from toolset.adapters.tools.transform.text_template_tool import TextTemplateTool
from toolset.domain.exceptions import ToolExecutionError


# ── JsonTransformTool ─────────────────────────────────────────────────────────

class TestJsonTransformTool:
    @pytest.mark.asyncio
    async def test_simple_key_access(self):
        result = await JsonTransformTool().execute({"data": {"name": "Alice", "age": 30}, "expression": "name"})
        assert result["result"] == "Alice"
        assert result["matched"] is True

    @pytest.mark.asyncio
    async def test_nested_path(self):
        data = {"user": {"address": {"city": "Seoul"}}}
        result = await JsonTransformTool().execute({"data": data, "expression": "user.address.city"})
        assert result["result"] == "Seoul"

    @pytest.mark.asyncio
    async def test_array_index(self):
        data = {"items": [{"id": 1}, {"id": 2}]}
        result = await JsonTransformTool().execute({"data": data, "expression": "items[1].id"})
        assert result["result"] == 2

    @pytest.mark.asyncio
    async def test_missing_path_returns_not_matched(self):
        result = await JsonTransformTool().execute({"data": {"a": 1}, "expression": "b.c"})
        assert result["matched"] is False
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_empty_expression_raises(self):
        with pytest.raises(ToolExecutionError):
            await JsonTransformTool().execute({"data": {}, "expression": "  "})


# ── TextTemplateTool ──────────────────────────────────────────────────────────

class TestTextTemplateTool:
    @pytest.mark.asyncio
    async def test_basic_rendering(self):
        result = await TextTemplateTool().execute({
            "template": "Hello, {name}! You are {age} years old.",
            "variables": {"name": "Alice", "age": 30},
        })
        assert result["rendered"] == "Hello, Alice! You are 30 years old."

    @pytest.mark.asyncio
    async def test_missing_variable_raises(self):
        with pytest.raises(ToolExecutionError):
            await TextTemplateTool().execute({
                "template": "Hello, {name}! From {sender}.",
                "variables": {"name": "Alice"},
            })

    @pytest.mark.asyncio
    async def test_no_variables_plain_string(self):
        result = await TextTemplateTool().execute({"template": "No variables here.", "variables": {}})
        assert result["rendered"] == "No variables here."


# ── DataMappingTool ───────────────────────────────────────────────────────────

class TestDataMappingTool:
    @pytest.mark.asyncio
    async def test_basic_rename(self):
        result = await DataMappingTool().execute({
            "data": {"first_name": "Alice", "last_name": "Kim"},
            "mapping": {"first_name": "firstName", "last_name": "lastName"},
        })
        assert result["result"] == {"firstName": "Alice", "lastName": "Kim"}
        assert result["mapped_count"] == 2

    @pytest.mark.asyncio
    async def test_unmapped_fields_preserved_by_default(self):
        result = await DataMappingTool().execute({
            "data": {"a": 1, "b": 2},
            "mapping": {"a": "x"},
        })
        assert "b" in result["result"]
        assert result["result"]["x"] == 1

    @pytest.mark.asyncio
    async def test_drop_unmapped(self):
        result = await DataMappingTool().execute({
            "data": {"a": 1, "b": 2},
            "mapping": {"a": "x"},
            "drop_unmapped": True,
        })
        assert result["result"] == {"x": 1}

    @pytest.mark.asyncio
    async def test_non_dict_data_raises(self):
        with pytest.raises(ToolExecutionError):
            await DataMappingTool().execute({"data": [1, 2, 3], "mapping": {}})
