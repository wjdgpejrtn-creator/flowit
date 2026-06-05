"""WorkflowExplanationService 단위 테스트."""
from __future__ import annotations

from uuid import uuid4

import pytest

from common_schemas.agent import DraftSpec, SlotFillingState
from common_schemas.enums import RiskLevel
from common_schemas.workflow import Edge, NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.workflow_explanation import WorkflowExplanation

from ai_agent.domain.services.workflow_explanation_service import WorkflowExplanationService


# ------------------------------------------------------------------ fixtures


def _make_config(
    *,
    name: str = "TestNode",
    description: str = "설명",
    risk_level: RiskLevel = RiskLevel.LOW,
    required_connections: list[str] | None = None,
) -> NodeConfig:
    return NodeConfig(
        node_id=uuid4(),
        node_type="test_type",
        name=name,
        category="test",
        version="1.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=risk_level,
        required_connections=required_connections or [],
        description=description,
        is_mvp=True,
    )


def _make_instance(node_id, *, parameters: dict | None = None) -> NodeInstance:
    return NodeInstance(
        instance_id=uuid4(),
        node_id=node_id,
        parameters=parameters or {},
        position=Position(x=0.0, y=0.0),
    )


def _make_spec(intent: str = "슬랙 알림 전송") -> DraftSpec:
    return DraftSpec(
        natural_language_intent=intent,
        unresolved_nodes=[],
        discovered_entities={},
        slot_filling_state=SlotFillingState(asked=[], pending=[], filled={}),
        consultant_turn_count=0,
    )


def _make_workflow(nodes: list[NodeInstance], connections: list[Edge]) -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="Test",
        scope="private",
        is_draft=True,
        nodes=nodes,
        connections=connections,
        owner_user_id=uuid4(),
    )


# ------------------------------------------------------------------ tests


class TestEmptyWorkflow:
    def test_empty_nodes_returns_valid_explanation(self):
        svc = WorkflowExplanationService()
        workflow = _make_workflow([], [])
        result = svc.explain(workflow, _make_spec(), [])
        assert isinstance(result, WorkflowExplanation)
        assert result.steps == []
        assert result.permissions == []
        assert result.assumptions == []

    def test_intent_restatement_equals_spec_intent(self):
        svc = WorkflowExplanationService()
        intent = "매일 오전 9시 보고서 발송"
        workflow = _make_workflow([], [])
        result = svc.explain(workflow, _make_spec(intent), [])
        assert result.intent_restatement == intent

    def test_summary_contains_node_count(self):
        svc = WorkflowExplanationService()
        workflow = _make_workflow([], [])
        result = svc.explain(workflow, _make_spec(), [])
        assert "0개 노드" in result.summary


class TestTopologicalOrder:
    def test_two_node_chain_ordered_correctly(self):
        """A → B 연결에서 steps[0]=A, steps[1]=B."""
        cfg_a = _make_config(name="NodeA")
        cfg_b = _make_config(name="NodeB")
        inst_a = _make_instance(cfg_a.node_id)
        inst_b = _make_instance(cfg_b.node_id)
        edge = Edge(
            from_instance_id=inst_a.instance_id,
            to_instance_id=inst_b.instance_id,
            from_handle="out",
            to_handle="in",
        )
        workflow = _make_workflow([inst_b, inst_a], [edge])  # 의도적으로 역순 입력
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg_a, cfg_b])
        assert result.steps[0].node_name == "NodeA"
        assert result.steps[1].node_name == "NodeB"

    def test_steps_are_one_based(self):
        cfg = _make_config(name="Solo")
        inst = _make_instance(cfg.node_id)
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg])
        assert result.steps[0].order == 1

    def test_three_node_linear_order(self):
        """A → B → C 순서 확인."""
        cfgs = [_make_config(name=n) for n in ("First", "Second", "Third")]
        insts = [_make_instance(c.node_id) for c in cfgs]
        edges = [
            Edge(from_instance_id=insts[0].instance_id, to_instance_id=insts[1].instance_id,
                 from_handle="out", to_handle="in"),
            Edge(from_instance_id=insts[1].instance_id, to_instance_id=insts[2].instance_id,
                 from_handle="out", to_handle="in"),
        ]
        workflow = _make_workflow(list(reversed(insts)), edges)
        result = WorkflowExplanationService().explain(workflow, _make_spec(), cfgs)
        names = [s.node_name for s in result.steps]
        assert names == ["First", "Second", "Third"]

    def test_cycle_falls_back_to_original_order(self):
        """사이클이 있으면 원래 nodes 순서로 반환 (크래시 없음)."""
        cfgs = [_make_config(name=n) for n in ("A", "B")]
        insts = [_make_instance(c.node_id) for c in cfgs]
        edges = [
            Edge(from_instance_id=insts[0].instance_id, to_instance_id=insts[1].instance_id,
                 from_handle="out", to_handle="in"),
            Edge(from_instance_id=insts[1].instance_id, to_instance_id=insts[0].instance_id,
                 from_handle="out", to_handle="in"),
        ]
        workflow = _make_workflow(insts, edges)
        result = WorkflowExplanationService().explain(workflow, _make_spec(), cfgs)
        assert len(result.steps) == 2  # 크래시 없이 2개 반환


class TestPermissions:
    def test_required_connections_become_permissions(self):
        cfg = _make_config(name="SlackNode", required_connections=["slack"])
        inst = _make_instance(cfg.node_id)
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg])
        assert len(result.permissions) == 1
        assert result.permissions[0].connection == "slack"
        assert result.permissions[0].node_name == "SlackNode"

    def test_same_connection_different_nodes_not_deduplicated(self):
        """같은 connection이라도 다른 노드면 별도 PermissionItem."""
        cfg_a = _make_config(name="Slack1", required_connections=["slack"])
        cfg_b = _make_config(name="Slack2", required_connections=["slack"])
        insts = [_make_instance(cfg_a.node_id), _make_instance(cfg_b.node_id)]
        workflow = _make_workflow(insts, [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg_a, cfg_b])
        assert len(result.permissions) == 2

    def test_same_node_same_connection_deduplicated(self):
        """동일 (connection, node_name) 쌍은 1회만."""
        cfg = _make_config(name="Node", required_connections=["slack", "slack"])
        inst = _make_instance(cfg.node_id)
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg])
        slack_items = [p for p in result.permissions if p.connection == "slack"]
        assert len(slack_items) == 1

    def test_no_connections_yields_empty_permissions(self):
        cfg = _make_config(required_connections=[])
        inst = _make_instance(cfg.node_id)
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg])
        assert result.permissions == []

    def test_permission_risk_level_matches_node(self):
        cfg = _make_config(name="HighRiskNode", risk_level=RiskLevel.HIGH,
                           required_connections=["google_sheets"])
        inst = _make_instance(cfg.node_id)
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg])
        assert result.permissions[0].risk_level == RiskLevel.HIGH


class TestAssumptions:
    def test_empty_string_param_generates_assumption(self):
        cfg = _make_config(name="Notifier")
        inst = _make_instance(cfg.node_id, parameters={"channel": ""})
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg])
        assert len(result.assumptions) == 1
        assert "Notifier" in result.assumptions[0]
        assert "channel" in result.assumptions[0]

    def test_none_param_generates_assumption(self):
        cfg = _make_config(name="Sender")
        inst = _make_instance(cfg.node_id, parameters={"recipient": None})
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg])
        assert any("recipient" in a for a in result.assumptions)

    def test_filled_param_does_not_generate_assumption(self):
        cfg = _make_config(name="Sender")
        inst = _make_instance(cfg.node_id, parameters={"channel": "#general"})
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg])
        assert result.assumptions == []

    def test_multiple_empty_params_multiple_assumptions(self):
        cfg = _make_config(name="Node")
        inst = _make_instance(cfg.node_id, parameters={"a": "", "b": "", "c": "filled"})
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg])
        assert len(result.assumptions) == 2


class TestStepFields:
    def test_step_description_from_node_config(self):
        cfg = _make_config(name="MyNode", description="슬랙 채널에 메시지를 전송합니다.")
        inst = _make_instance(cfg.node_id)
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg])
        assert result.steps[0].description == "슬랙 채널에 메시지를 전송합니다."

    def test_step_risk_level_from_node_config(self):
        cfg = _make_config(risk_level=RiskLevel.MEDIUM)
        inst = _make_instance(cfg.node_id)
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [cfg])
        assert result.steps[0].risk_level == RiskLevel.MEDIUM

    def test_unknown_node_config_uses_fallback(self):
        """node_configs에 없는 node_id면 크래시 없이 fallback 사용."""
        inst = _make_instance(uuid4())  # config 없는 instance
        workflow = _make_workflow([inst], [])
        result = WorkflowExplanationService().explain(workflow, _make_spec(), [])
        assert len(result.steps) == 1
        assert result.steps[0].risk_level == RiskLevel.LOW
