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
    assert node.owner_user_id is None
    assert node.team_id is None


def test_node_definition_with_service_type():
    node = _make_node(service_type="google_workspace")
    assert node.service_type == "google_workspace"


def test_node_definition_global_scope_when_owner_and_team_none():
    # ADR-0020 (i): owner/team 둘 다 None = company 전역(기존 53종). 비침습.
    node = _make_node()
    assert node.owner_user_id is None and node.team_id is None


def test_node_definition_personal_scope():
    uid = uuid4()
    node = _make_node(owner_user_id=uid)
    assert node.owner_user_id == uid
    assert node.team_id is None


def test_node_definition_team_scope():
    tid = uuid4()
    node = _make_node(team_id=tid)
    assert node.team_id == tid
    assert node.owner_user_id is None


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
