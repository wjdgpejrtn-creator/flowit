from uuid import uuid4

from common_schemas.enums import RiskLevel
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.entities.node_metadata import NodeMetadata


def _make_node(**kwargs) -> NodeDefinition:
    defaults = dict(
        node_id=uuid4(), node_type="test_node", name="Test Node", category="테스트",
        version="1.0.0", input_schema={}, output_schema={}, parameter_schema={},
        risk_level=RiskLevel.LOW, required_connections=[], description="테스트 노드", is_mvp=True,
    )
    return NodeDefinition(**{**defaults, **kwargs})


def test_node_definition_creation():
    node = _make_node(node_type="gmail_send", risk_level=RiskLevel.HIGH)
    assert node.node_type == "gmail_send"
    assert node.risk_level == RiskLevel.HIGH
    assert node.is_mvp is True


def test_node_definition_required_connections():
    node = _make_node(required_connections=["google", "slack"])
    assert "google" in node.required_connections
    assert "slack" in node.required_connections


def test_node_definition_optional_fields_default_none():
    node = _make_node()
    assert node.service_type is None
    assert node.embedding is None


def test_node_definition_with_service_type():
    node = _make_node(service_type="google_workspace")
    assert node.service_type == "google_workspace"


def test_node_metadata_is_frozen():
    meta = NodeMetadata(
        node_id=uuid4(), name="Test", category="AI",
        risk_level=RiskLevel.LOW, is_mvp=True,
    )
    try:
        meta.name = "Changed"  # type: ignore
        assert False, "Should be frozen"
    except Exception:
        pass
