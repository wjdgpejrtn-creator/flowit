"""WorkflowEditService(refine 결정적 applier) 순수 단위테스트 — mock 불필요."""
from uuid import uuid4

import pytest
from common_schemas import Edge, NodeConfig, NodeInstance, Position, WorkflowSchema
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError

from ai_agent.domain.services.workflow_edit_service import (
    AddNodeOp,
    EditPlan,
    RemoveNodeOp,
    ReplaceNodeOp,
    SetParamOp,
    WorkflowEditService,
)


def _cfg(node_type: str, *, outputs: list[str] | None = None) -> NodeConfig:
    return NodeConfig(
        node_id=uuid4(),
        node_type=node_type,
        name=node_type,
        category="test",
        version="1.0",
        description="",
        input_schema={},
        output_schema={"properties": {o: {"type": "string"} for o in (outputs or [])}},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        is_mvp=True,
    )


def _node(cfg: NodeConfig, params: dict | None = None) -> NodeInstance:
    return NodeInstance(
        instance_id=uuid4(), node_id=cfg.node_id,
        parameters=params or {}, position=Position(x=1.0, y=2.0),
    )


def _wf(nodes: list[NodeInstance], edges: list[Edge]) -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(), name="Prior", scope="private", is_draft=False,
        owner_user_id=uuid4(), nodes=nodes, connections=edges,
    )


def _edge(a: NodeInstance, b: NodeInstance) -> Edge:
    return Edge(from_instance_id=a.instance_id, to_instance_id=b.instance_id,
                from_handle="output", to_handle="input")


class TestSetParam:
    def test_merges_params_preserving_identity_and_edges(self):
        sheets, slack = _cfg("google_sheets_read"), _cfg("slack_post_message")
        n0, n1 = _node(sheets), _node(slack, {"channel": "#general", "text": "hi"})
        prior = _wf([n0, n1], [_edge(n0, n1)])
        svc = WorkflowEditService()

        plan = EditPlan(ops=[SetParamOp(op="set_param", target_ref="n1", parameters={"channel": "#alerts"})])
        out = svc.apply(prior, plan, [sheets, slack])

        edited = next(n for n in out.nodes if n.instance_id == n1.instance_id)
        assert edited.parameters == {"channel": "#alerts", "text": "hi"}  # 병합(text 보존)
        assert edited.node_id == slack.node_id                            # 정체성 보존
        assert edited.position == Position(x=1.0, y=2.0)
        assert len(out.connections) == 1 and out.workflow_id == prior.workflow_id
        assert out.is_draft is True


class TestReplaceNode:
    def test_swaps_node_id_keeps_instance_id_so_edges_survive(self):
        sheets, slack, gmail = _cfg("google_sheets_read"), _cfg("slack_post_message"), _cfg("gmail_send")
        n0, n1 = _node(sheets), _node(slack, {"channel": "#general"})
        n1 = n1.model_copy(update={"credential_ids": {"slack": uuid4()}})
        prior = _wf([n0, n1], [_edge(n0, n1)])
        svc = WorkflowEditService()

        out = svc.apply(
            prior,
            EditPlan(ops=[ReplaceNodeOp(op="replace_node", target_ref="n1", new_node_type="gmail_send",
                                        parameters={"to": "a@b.com", "subject": "S"})]),
            [sheets, slack, gmail],
        )

        repl = next(n for n in out.nodes if n.instance_id == n1.instance_id)
        assert repl.instance_id == n1.instance_id          # instance_id 유지
        assert repl.node_id == gmail.node_id               # node_type 교체
        assert repl.parameters == {"to": "a@b.com", "subject": "S"}
        assert repl.credential_ids == {} and repl.credential_id is None  # creds 초기화
        # 엣지가 instance_id 그대로라 자동 생존
        assert len(out.connections) == 1
        assert out.connections[0].to_instance_id == n1.instance_id

    def test_unknown_new_type_raises(self):
        slack = _cfg("slack_post_message")
        n0 = _node(slack)
        prior = _wf([n0], [])
        with pytest.raises(ExecutionError) as ei:
            WorkflowEditService().apply(
                prior, EditPlan(ops=[ReplaceNodeOp(op="replace_node", target_ref="n0", new_node_type="nonexistent")]),
                [slack],
            )
        assert ei.value.code == "E_UNKNOWN_NODE_TYPE"

    def test_regrounds_downstream_ref_when_output_fields_change(self):
        # n0(slack out=["ts"]) → n1이 ${n0.ts} 참조. n0를 gmail(out=["message_id"])로 교체 →
        # 단일 출력이므로 하류 참조가 message_id로 보정돼야 한다.
        slack = _cfg("slack_post_message", outputs=["ts"])
        gmail = _cfg("gmail_send", outputs=["message_id"])
        http = _cfg("http_request")
        n0 = _node(slack)
        n1 = _node(http, {"url": f"${{{n0.instance_id}.ts}}"})
        prior = _wf([n0, n1], [_edge(n0, n1)])

        out = WorkflowEditService().apply(
            prior, EditPlan(ops=[ReplaceNodeOp(op="replace_node", target_ref="n0", new_node_type="gmail_send")]),
            [slack, gmail, http],
        )
        downstream = next(n for n in out.nodes if n.instance_id == n1.instance_id)
        assert downstream.parameters["url"] == f"${{{n0.instance_id}.message_id}}"


class TestPlannerRefRewrite:
    """planner가 값 참조를 ${nX.field}(임시 ref)로 내므로 apply가 instance_id로 역번역해야 한다.
    이 패스가 빠져 set_param/replace_node가 넣은 ${n2.content}가 그대로 누출되던 회귀 방지."""

    def test_set_param_value_ref_rewritten_to_instance_id(self):
        gemma = _cfg("gemma_chat", outputs=["content"])
        gmail = _cfg("gmail_send")
        n0, n1 = _node(gemma), _node(gmail, {"to": ["a@b.com"]})
        prior = _wf([n0, n1], [_edge(n0, n1)])

        out = WorkflowEditService().apply(
            prior,
            EditPlan(ops=[SetParamOp(op="set_param", target_ref="n1",
                                     parameters={"body": "${n0.content}"})]),
            [gemma, gmail],
        )
        edited = next(n for n in out.nodes if n.instance_id == n1.instance_id)
        # ${n0.content} → ${<gemma instance_id>.content} (런타임 ReferenceResolver가 풀 수 있는 형식)
        assert edited.parameters["body"] == f"${{{n0.instance_id}.content}}"

    def test_replace_node_value_ref_rewritten(self):
        gemma = _cfg("gemma_chat", outputs=["content"])
        slack, gmail = _cfg("slack_post_message"), _cfg("gmail_send")
        n0, n1 = _node(gemma), _node(slack, {"channel": "#g", "text": "${n0.content}"})
        prior = _wf([n0, n1], [_edge(n0, n1)])

        out = WorkflowEditService().apply(
            prior,
            EditPlan(ops=[ReplaceNodeOp(op="replace_node", target_ref="n1", new_node_type="gmail_send",
                                        parameters={"to": ["a@b.com"], "body": "${n0.content}"})]),
            [gemma, slack, gmail],
        )
        repl = next(n for n in out.nodes if n.instance_id == n1.instance_id)
        assert repl.parameters["body"] == f"${{{n0.instance_id}.content}}"

    def test_existing_instance_id_ref_preserved(self):
        # 안 건드린 노드의 ${instance_id.field}는 n0..nX 키와 안 겹쳐 무손상(이중 변환 X)이어야 한다.
        gemma = _cfg("gemma_chat", outputs=["content"])
        gmail = _cfg("gmail_send")
        n0 = _node(gemma)
        n1 = _node(gmail, {"to": ["a@b.com"], "body": f"${{{n0.instance_id}.content}}"})
        prior = _wf([n0, n1], [_edge(n0, n1)])

        out = WorkflowEditService().apply(
            prior,
            EditPlan(ops=[SetParamOp(op="set_param", target_ref="n0", parameters={"prompt": "hi"})]),
            [gemma, gmail],
        )
        downstream = next(n for n in out.nodes if n.instance_id == n1.instance_id)
        assert downstream.parameters["body"] == f"${{{n0.instance_id}.content}}"


class TestAddNode:
    def test_after_ref_on_sink_appends_single_edge(self):
        sheets, slack = _cfg("google_sheets_read"), _cfg("slack_post_message")
        n0 = _node(sheets)
        prior = _wf([n0], [])  # n0 단독(sink)
        out = WorkflowEditService().apply(
            prior, EditPlan(ops=[AddNodeOp(op="add_node", new_node_type="slack_post_message", after_ref="n0")]),
            [sheets, slack],
        )
        assert len(out.nodes) == 2
        new = next(n for n in out.nodes if n.node_id == slack.node_id)
        assert len(out.connections) == 1
        assert out.connections[0].from_instance_id == n0.instance_id
        assert out.connections[0].to_instance_id == new.instance_id

    def test_after_ref_midchain_rewires(self):
        # a→b 에서 a 뒤에 new 삽입 → a→new→b
        a, b, c = _cfg("a"), _cfg("b"), _cfg("c")
        na, nb = _node(a), _node(b)
        prior = _wf([na, nb], [_edge(na, nb)])
        out = WorkflowEditService().apply(
            prior, EditPlan(ops=[AddNodeOp(op="add_node", new_node_type="c", after_ref="n0")]),
            [a, b, c],
        )
        new = next(n for n in out.nodes if n.node_id == c.node_id)
        pairs = {(e.from_instance_id, e.to_instance_id) for e in out.connections}
        assert (na.instance_id, new.instance_id) in pairs
        assert (new.instance_id, nb.instance_id) in pairs
        assert (na.instance_id, nb.instance_id) not in pairs  # 원래 직결 제거됨

    def test_no_anchor_raises_dangling(self):
        a = _cfg("a")
        prior = _wf([_node(a)], [])
        with pytest.raises(ExecutionError) as ei:
            WorkflowEditService().apply(
                prior, EditPlan(ops=[AddNodeOp(op="add_node", new_node_type="a")]), [a]
            )
        assert ei.value.code == "E_REFINE_DANGLING"


class TestRemoveNode:
    def test_middle_node_bridges(self):
        # a→b→c, b 제거 → a→c
        a, b, c = _cfg("a"), _cfg("b"), _cfg("c")
        na, nb, nc = _node(a), _node(b), _node(c)
        prior = _wf([na, nb, nc], [_edge(na, nb), _edge(nb, nc)])
        out = WorkflowEditService().apply(
            prior, EditPlan(ops=[RemoveNodeOp(op="remove_node", target_ref="n1")]), [a, b, c]
        )
        assert {n.instance_id for n in out.nodes} == {na.instance_id, nc.instance_id}
        assert len(out.connections) == 1
        bridge = out.connections[0]
        assert (bridge.from_instance_id, bridge.to_instance_id) == (na.instance_id, nc.instance_id)

    def test_sink_removal_leaves_no_orphan_edge(self):
        a, b = _cfg("a"), _cfg("b")
        na, nb = _node(a), _node(b)
        prior = _wf([na, nb], [_edge(na, nb)])
        out = WorkflowEditService().apply(
            prior, EditPlan(ops=[RemoveNodeOp(op="remove_node", target_ref="n1")]), [a, b]
        )
        assert {n.instance_id for n in out.nodes} == {na.instance_id}
        assert out.connections == []


class TestGeneral:
    def test_bad_ref_raises(self):
        a = _cfg("a")
        prior = _wf([_node(a)], [])
        with pytest.raises(ExecutionError) as ei:
            WorkflowEditService().apply(
                prior, EditPlan(ops=[SetParamOp(op="set_param", target_ref="n9", parameters={})]), [a]
            )
        assert ei.value.code == "E_REFINE_BAD_REF"

    def test_rename_and_prior_unmutated(self):
        a = _cfg("a")
        na = _node(a, {"k": "v"})
        prior = _wf([na], [])
        out = WorkflowEditService().apply(
            prior,
            EditPlan(name="새 이름", ops=[SetParamOp(op="set_param", target_ref="n0", parameters={"k": "v2"})]),
            [a],
        )
        assert out.name == "새 이름"
        assert out.workflow_id == prior.workflow_id
        # workflow_id 유지 시 저장은 UPDATE(merge) → version NOT NULL 충족 위해 +1 (None→1).
        assert out.version == 1
        # prior(frozen) 원본 불변
        assert prior.nodes[0].parameters == {"k": "v"}
        assert prior.name == "Prior"

    def test_empty_ops_is_noop_copy(self):
        a = _cfg("a")
        prior = _wf([_node(a, {"k": "v"})], [])
        out = WorkflowEditService().apply(prior, EditPlan(ops=[]), [a])
        assert out.workflow_id == prior.workflow_id
        assert out.is_draft is True
        assert out.nodes[0].parameters == {"k": "v"}
