from common_schemas.enums import RiskLevel

from skills_marketplace.domain.value_objects.node_spec_staging import NodeSpecStaging


def test_node_spec_staging_creation_defaults():
    s = NodeSpecStaging(
        category="action",
        input_schema={},
        output_schema={},
        risk_level=RiskLevel.LOW,
    )
    assert s.category == "action"
    assert s.required_connections == []
    assert s.service_type is None


def test_node_spec_staging_full():
    s = NodeSpecStaging(
        category="integration",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        risk_level=RiskLevel.HIGH,
        required_connections=["google", "slack"],
        service_type="google_workspace",
    )
    assert s.required_connections == ["google", "slack"]
    assert s.service_type == "google_workspace"
    assert s.risk_level == RiskLevel.HIGH


def test_node_spec_staging_frozen():
    s = NodeSpecStaging(category="action", input_schema={}, output_schema={}, risk_level=RiskLevel.LOW)
    try:
        s.category = "changed"  # type: ignore[misc]
        raise AssertionError("NodeSpecStaging should be frozen")
    except Exception:
        pass
