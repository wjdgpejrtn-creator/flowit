from __future__ import annotations

import pytest

from toolset.adapters.tools.control.conditional_tool import ConditionalTool
from toolset.adapters.tools.control.loop_tool import LoopTool
from toolset.domain.exceptions import ToolExecutionError


# ── ConditionalTool ───────────────────────────────────────────────────────────

class TestConditionalTool:
    @pytest.mark.asyncio
    async def test_eq_true(self):
        result = await ConditionalTool().execute({"left": 5, "operator": "eq", "right": 5})
        assert result["result"] is True
        assert result["branch"] == "true_branch"

    @pytest.mark.asyncio
    async def test_eq_false(self):
        result = await ConditionalTool().execute({"left": 5, "operator": "eq", "right": 3})
        assert result["result"] is False
        assert result["branch"] == "false_branch"

    @pytest.mark.asyncio
    async def test_gt(self):
        result = await ConditionalTool().execute({"left": 10, "operator": "gt", "right": 5})
        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_lt(self):
        result = await ConditionalTool().execute({"left": 3, "operator": "lt", "right": 10})
        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_contains_string(self):
        result = await ConditionalTool().execute({"left": "hello world", "operator": "contains", "right": "world"})
        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_startswith(self):
        result = await ConditionalTool().execute({"left": "hello", "operator": "startswith", "right": "he"})
        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_in_list(self):
        result = await ConditionalTool().execute({"left": "apple", "operator": "in", "right": ["apple", "banana"]})
        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_unknown_operator_raises(self):
        with pytest.raises(ToolExecutionError):
            await ConditionalTool().execute({"left": 1, "operator": "unknown_op", "right": 1})

    @pytest.mark.asyncio
    async def test_type_error_raises(self):
        with pytest.raises(ToolExecutionError):
            await ConditionalTool().execute({"left": "text", "operator": "gt", "right": 5})


# ── LoopTool ──────────────────────────────────────────────────────────────────

class TestLoopTool:
    @pytest.mark.asyncio
    async def test_basic_iteration(self):
        result = await LoopTool().execute({"items": ["a", "b", "c"]})
        assert result["count"] == 3
        assert result["results"][0] == {"index": 0, "item": "a"}
        assert result["results"][2] == {"index": 2, "item": "c"}

    @pytest.mark.asyncio
    async def test_max_iterations_cap(self):
        items = list(range(200))
        result = await LoopTool().execute({"items": items, "max_iterations": 50})
        assert result["count"] == 50

    @pytest.mark.asyncio
    async def test_empty_list(self):
        result = await LoopTool().execute({"items": []})
        assert result["count"] == 0
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_non_list_raises(self):
        with pytest.raises(ToolExecutionError):
            await LoopTool().execute({"items": "not a list"})

