"""WorkflowEditPlanner 단위테스트 — LLMPort mock으로 op 파싱·프롬프트 구성 검증."""
from unittest.mock import AsyncMock

import pytest
from common_schemas.exceptions import ExecutionError

from ai_agent.domain.ports import LLMPort
from ai_agent.domain.services.workflow_edit_planner import WorkflowEditPlanner
from ai_agent.domain.services.workflow_edit_service import (
    AddNodeOp,
    EditPlan,
    RemoveNodeOp,
    ReplaceNodeOp,
    SetParamOp,
)

_PRIOR = {
    "name": "WF",
    "nodes": [{"ref": "n0", "node_type": "slack_post_message", "parameters": {}}],
    "connections": [],
}
_CATALOG = [{"node_type": "gmail_send", "name": "Gmail", "input_schema": {}, "outputs": ["message_id"]}]


def _mock_llm(plan: EditPlan) -> LLMPort:
    llm = AsyncMock(spec=LLMPort)
    llm.generate_structured = AsyncMock(return_value=plan)
    return llm


class TestWorkflowEditPlanner:
    @pytest.mark.asyncio
    async def test_parses_each_op_via_discriminated_union(self):
        plan = EditPlan(ops=[
            SetParamOp(op="set_param", target_ref="n0", parameters={"channel": "#x"}),
            ReplaceNodeOp(op="replace_node", target_ref="n0", new_node_type="gmail_send", parameters={"to": "a@b"}),
            AddNodeOp(op="add_node", new_node_type="gmail_send", after_ref="n0"),
            RemoveNodeOp(op="remove_node", target_ref="n0"),
        ])
        out = await WorkflowEditPlanner(_mock_llm(plan)).plan(_PRIOR, _CATALOG, "고쳐줘")
        assert [type(o) for o in out.ops] == [SetParamOp, ReplaceNodeOp, AddNodeOp, RemoveNodeOp]

    @pytest.mark.asyncio
    async def test_prompt_contains_workflow_catalog_instruction(self):
        llm = _mock_llm(EditPlan(ops=[]))
        await WorkflowEditPlanner(llm).plan(_PRIOR, _CATALOG, "slack말고 gmail로 변경해줘")
        prompt = llm.generate_structured.call_args.args[0]
        assert "CURRENT WORKFLOW" in prompt
        assert "Available nodes" in prompt
        assert "slack말고 gmail로 변경해줘" in prompt
        assert "gmail_send" in prompt          # 카탈로그 직렬화
        assert "replace_node" in prompt        # op 가이드
        assert "말고" in prompt                # 부정 가이드(replace, not add)

    @pytest.mark.asyncio
    async def test_retry_feedback_injected(self):
        llm = _mock_llm(EditPlan(ops=[]))
        await WorkflowEditPlanner(llm).plan(_PRIOR, _CATALOG, "고쳐줘", retry_feedback="unknown node_type: foo")
        prompt = llm.generate_structured.call_args.args[0]
        assert "unknown node_type: foo" in prompt

    @pytest.mark.asyncio
    async def test_llm_failure_wrapped(self):
        llm = AsyncMock(spec=LLMPort)
        llm.generate_structured = AsyncMock(side_effect=Exception("boom"))
        with pytest.raises(ExecutionError) as ei:
            await WorkflowEditPlanner(llm).plan(_PRIOR, _CATALOG, "고쳐줘")
        assert ei.value.code == "E_REFINE_PLAN_PARSE"
