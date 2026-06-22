from uuid import uuid4

import pytest
from common_schemas import Edge, NodeInstance, Position, WorkflowSchema
from common_schemas.exceptions import ValidationError
from nodes_graph.domain.services.graph_serializer import GraphSerializer


def _make_workflow() -> WorkflowSchema:
    n1_id = uuid4()
    n2_id = uuid4()
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="직렬화 테스트",
        description="test",
        scope="private",
        is_draft=False,
        nodes=[
            NodeInstance(instance_id=n1_id, node_id=uuid4(), parameters={}, position=Position(x=0.0, y=0.0)),
            NodeInstance(instance_id=n2_id, node_id=uuid4(), parameters={}, position=Position(x=1.0, y=1.0)),
        ],
        connections=[
            Edge(from_instance_id=n1_id, to_instance_id=n2_id, from_handle="out", to_handle="in"),
        ],
    )


def test_serialize_returns_dict():
    serializer = GraphSerializer()
    workflow = _make_workflow()
    result = serializer.serialize(workflow)

    assert isinstance(result, dict)
    assert "workflow_id" in result
    assert "nodes" in result
    assert "connections" in result


def test_deserialize_roundtrip():
    serializer = GraphSerializer()
    workflow = _make_workflow()
    data = serializer.serialize(workflow)
    restored = serializer.deserialize(data)

    assert restored.workflow_id == workflow.workflow_id
    assert len(restored.nodes) == len(workflow.nodes)
    assert len(restored.connections) == len(workflow.connections)
    assert restored.name == workflow.name


def test_deserialize_invalid_data_raises():
    serializer = GraphSerializer()
    with pytest.raises(ValidationError):
        serializer.deserialize({"invalid": "data"})
