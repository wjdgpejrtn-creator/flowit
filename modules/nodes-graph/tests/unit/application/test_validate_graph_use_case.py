from uuid import uuid4

import pytest
from common_schemas import Edge, NodeInstance, Position, WorkflowSchema
from nodes_graph.application.use_cases.validate_graph_use_case import ValidateGraphUseCase
from nodes_graph.domain.services.graph_validator import GraphValidator


class _Repo:
    async def upsert(self, d): return d
    async def list_all(self, mvp_only=False): return []
    async def get_by_id(self, node_id): return None
    async def search_by_embedding(self, q, limit=10): return []


def _wf(nodes, edges):
    return WorkflowSchema(
        workflow_id=uuid4(), name="test", scope="private", is_draft=False,
        nodes=nodes, connections=edges,
    )


def _node():
    return NodeInstance(instance_id=uuid4(), node_id=uuid4(), parameters={}, position=Position(x=0, y=0))


def _edge(f, t):
    return Edge(from_instance_id=f, to_instance_id=t, from_handle="out", to_handle="in")


@pytest.mark.asyncio
async def test_valid_workflow_passes():
    n1, n2 = _node(), _node()
    uc = ValidateGraphUseCase(GraphValidator(_Repo()))
    result = await uc.execute(_wf([n1, n2], [_edge(n1.instance_id, n2.instance_id)]))
    assert result.validation_status == "passed"


@pytest.mark.asyncio
async def test_dangling_edge_fails():
    n1 = _node()
    bad_edge = Edge(from_instance_id=n1.instance_id, to_instance_id=uuid4(), from_handle="out", to_handle="in")
    uc = ValidateGraphUseCase(GraphValidator(_Repo()))
    result = await uc.execute(_wf([n1], [bad_edge]))
    assert result.validation_status == "failed"


@pytest.mark.asyncio
async def test_cyclic_workflow_fails():
    n1, n2 = _node(), _node()
    edges = [_edge(n1.instance_id, n2.instance_id), _edge(n2.instance_id, n1.instance_id)]
    uc = ValidateGraphUseCase(GraphValidator(_Repo()))
    result = await uc.execute(_wf([n1, n2], edges))
    assert result.validation_status == "failed"
