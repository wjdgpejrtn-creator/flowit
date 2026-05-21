from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas import NodeContext

from nodes_graph.domain.catalog.control.if_condition import IfConditionInput, IfConditionNode
from nodes_graph.domain.catalog.control.loop_count import LoopCountInput, LoopCountNode
from nodes_graph.domain.catalog.control.loop_list import LoopListInput, LoopListNode
from nodes_graph.domain.catalog.control.merge_branch import MergeBranchInput, MergeBranchNode
from nodes_graph.domain.catalog.control.retry import RetryInput, RetryNode
from nodes_graph.domain.catalog.control.stop_workflow import StopWorkflowError, StopWorkflowInput, StopWorkflowNode
from nodes_graph.domain.catalog.control.switch_case import SwitchCaseInput, SwitchCaseNode

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())


@pytest.mark.asyncio
async def test_if_condition_eq_true():
    node = IfConditionNode()
    out = await node.process(IfConditionInput(left=5, operator="eq", right=5, value="pass"), NODE_CTX)
    assert out.branch == "true"
    assert out.value == "pass"


@pytest.mark.asyncio
async def test_if_condition_eq_false():
    node = IfConditionNode()
    out = await node.process(IfConditionInput(left=5, operator="eq", right=3), NODE_CTX)
    assert out.branch == "false"


@pytest.mark.asyncio
async def test_if_condition_is_none():
    node = IfConditionNode()
    out = await node.process(IfConditionInput(left=None, operator="is_none"), NODE_CTX)
    assert out.branch == "true"


@pytest.mark.asyncio
async def test_if_condition_in():
    node = IfConditionNode()
    out = await node.process(IfConditionInput(left="a", operator="in", right=["a", "b", "c"]), NODE_CTX)
    assert out.branch == "true"


@pytest.mark.asyncio
async def test_switch_case_matched():
    node = SwitchCaseNode()
    out = await node.process(SwitchCaseInput(value="admin", cases=["admin", "user", "guest"]), NODE_CTX)
    assert out.matched_case == "admin"


@pytest.mark.asyncio
async def test_switch_case_default():
    node = SwitchCaseNode()
    out = await node.process(
        SwitchCaseInput(value="unknown", cases=["admin", "user"], default_case="default"), NODE_CTX
    )
    assert out.matched_case == "default"


@pytest.mark.asyncio
async def test_loop_list():
    node = LoopListNode()
    out = await node.process(LoopListInput(items=[1, 2, 3]), NODE_CTX)
    assert out.count == 3
    assert out.items == [1, 2, 3]


@pytest.mark.asyncio
async def test_loop_count():
    node = LoopCountNode()
    out = await node.process(LoopCountInput(count=3, start=1), NODE_CTX)
    assert out.count == 3
    assert out.indices == [1, 2, 3]


@pytest.mark.asyncio
async def test_retry_config():
    node = RetryNode()
    out = await node.process(
        RetryInput(max_attempts=5, delay_seconds=2.0, backoff_multiplier=3.0, value="data"), NODE_CTX
    )
    assert out.config["max_attempts"] == 5
    assert out.config["delay_seconds"] == 2.0
    assert out.value == "data"


@pytest.mark.asyncio
async def test_merge_branch_list():
    node = MergeBranchNode()
    out = await node.process(MergeBranchInput(branches=["a", "b", "c"], strategy="list"), NODE_CTX)
    assert out.result == ["a", "b", "c"]
    assert out.branch_count == 3


@pytest.mark.asyncio
async def test_merge_branch_dict_merge():
    node = MergeBranchNode()
    out = await node.process(MergeBranchInput(
        branches=[{"x": 1}, {"y": 2}],
        strategy="dict_merge",
    ), NODE_CTX)
    assert out.result == {"x": 1, "y": 2}


@pytest.mark.asyncio
async def test_merge_branch_first():
    node = MergeBranchNode()
    out = await node.process(MergeBranchInput(branches=["first", "second"], strategy="first"), NODE_CTX)
    assert out.result == "first"


@pytest.mark.asyncio
async def test_stop_workflow_raises():
    node = StopWorkflowNode()
    with pytest.raises(StopWorkflowError, match="테스트 종료"):
        await node.process(StopWorkflowInput(reason="테스트 종료"), NODE_CTX)
