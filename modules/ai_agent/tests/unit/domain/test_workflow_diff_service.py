"""WorkflowDiffService 단위 테스트 — 외부 의존성 없음."""
from __future__ import annotations

from uuid import uuid4

import pytest

from common_schemas import WorkflowSchema
from common_schemas.workflow import NodeInstance, Position
from ai_agent.domain.services.workflow_diff_service import WorkflowDiffService


def _make_node(node_id=None, instance_id=None, parameters=None) -> NodeInstance:
    return NodeInstance(
        instance_id=instance_id or uuid4(),
        node_id=node_id or uuid4(),
        parameters=parameters or {},
        position=Position(x=0, y=0),
    )


def _make_workflow(nodes, connections=None) -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="test",
        scope="private",
        is_draft=False,
        nodes=nodes,
        connections=connections or [],
    )


class TestWorkflowDiffService:
    def setup_method(self):
        self.svc = WorkflowDiffService()

    def test_identical_workflows_return_empty_diff(self):
        node = _make_node()
        wf = _make_workflow([node])
        diff = self.svc.compute(wf, wf)
        assert diff.is_empty()

    def test_detects_removed_node(self):
        node_a = _make_node()
        node_b = _make_node()
        draft = _make_workflow([node_a, node_b])
        final = _make_workflow([node_a])

        diff = self.svc.compute(draft, final)

        assert len(diff.removed_nodes) == 1
        assert diff.removed_nodes[0].instance_id == node_b.instance_id
        assert diff.removed_nodes[0].node_id == node_b.node_id
        assert diff.added_nodes == []

    def test_detects_added_node(self):
        node_a = _make_node()
        node_b = _make_node()
        draft = _make_workflow([node_a])
        final = _make_workflow([node_a, node_b])

        diff = self.svc.compute(draft, final)

        assert len(diff.added_nodes) == 1
        assert diff.added_nodes[0].instance_id == node_b.instance_id
        assert diff.added_nodes[0].node_id == node_b.node_id
        assert diff.removed_nodes == []

    def test_detects_parameter_change(self):
        instance_id = uuid4()
        node_id = uuid4()
        draft_node = _make_node(node_id=node_id, instance_id=instance_id, parameters={"channel": "slack"})
        final_node = _make_node(node_id=node_id, instance_id=instance_id, parameters={"channel": "teams"})

        diff = self.svc.compute(_make_workflow([draft_node]), _make_workflow([final_node]))

        assert len(diff.modified_params) == 1
        change = diff.modified_params[0]
        assert change.param_key == "channel"
        assert change.before == "slack"
        assert change.after == "teams"
        assert change.instance_id == instance_id
        assert change.node_id == node_id

    def test_detects_added_parameter(self):
        instance_id = uuid4()
        node_id = uuid4()
        draft_node = _make_node(node_id=node_id, instance_id=instance_id, parameters={})
        final_node = _make_node(node_id=node_id, instance_id=instance_id, parameters={"timeout": 30})

        diff = self.svc.compute(_make_workflow([draft_node]), _make_workflow([final_node]))

        assert len(diff.modified_params) == 1
        assert diff.modified_params[0].param_key == "timeout"
        assert diff.modified_params[0].before is None
        assert diff.modified_params[0].after == 30

    def test_to_feedback_lines_with_type_name(self):
        """node_type_name이 채워져 있으면 사람이 읽을 수 있는 출력."""
        from ai_agent.domain.services.workflow_diff_service import NodeDiff, WorkflowDiff
        node_id = uuid4()
        diff = WorkflowDiff(
            removed_nodes=[NodeDiff(instance_id=uuid4(), node_id=node_id, parameters={}, node_type_name="SlackNode")],
        )
        lines = diff.to_feedback_lines()
        assert len(lines) == 1
        assert "SlackNode" in lines[0]
        assert "삭제" in lines[0]

    def test_to_feedback_lines_fallback_to_uuid(self):
        """node_type_name 없으면 UUID fallback."""
        from ai_agent.domain.services.workflow_diff_service import NodeDiff, WorkflowDiff
        node_id = uuid4()
        diff = WorkflowDiff(
            added_nodes=[NodeDiff(instance_id=uuid4(), node_id=node_id, parameters={})],
        )
        lines = diff.to_feedback_lines()
        assert len(lines) == 1
        assert str(node_id) in lines[0]
        assert "추가" in lines[0]

    def test_to_feedback_lines_param_change(self):
        instance_id = uuid4()
        node_id = uuid4()
        draft_node = _make_node(node_id=node_id, instance_id=instance_id, parameters={"x": 1})
        final_node = _make_node(node_id=node_id, instance_id=instance_id, parameters={"x": 2})

        diff = self.svc.compute(_make_workflow([draft_node]), _make_workflow([final_node]))
        lines = diff.to_feedback_lines()

        assert len(lines) == 1
        assert "변경" in lines[0]

    def test_empty_workflows_return_empty_diff(self):
        draft = _make_workflow([])
        final = _make_workflow([])
        diff = self.svc.compute(draft, final)
        assert diff.is_empty()
