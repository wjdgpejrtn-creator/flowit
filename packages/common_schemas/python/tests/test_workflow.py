from uuid import uuid4

import pytest
from pydantic import ValidationError

from common_schemas.enums import RiskLevel
from common_schemas.workflow import Edge, NodeConfig, NodeInstance, Position, WorkflowSchema


class TestPosition:
    def test_create(self):
        pos = Position(x=1.0, y=2.0)
        assert pos.x == 1.0
        assert pos.y == 2.0

    def test_frozen(self):
        pos = Position(x=1.0, y=2.0)
        with pytest.raises(ValidationError):
            pos.x = 3.0


class TestEdge:
    def test_create(self):
        a, b = uuid4(), uuid4()
        edge = Edge(
            from_instance_id=a,
            to_instance_id=b,
            from_handle="out",
            to_handle="in",
        )
        assert edge.from_instance_id == a
        assert edge.to_instance_id == b


class TestNodeInstance:
    def test_create(self):
        ni = NodeInstance(
            instance_id=uuid4(),
            node_id=uuid4(),
            parameters={"key": "value"},
            position=Position(x=0, y=0),
        )
        assert ni.credential_id is None
        assert ni.skill_id is None
        assert ni.parameters == {"key": "value"}

    def test_skill_id_binding(self):
        skill = uuid4()
        ni = NodeInstance(
            instance_id=uuid4(),
            node_id=uuid4(),
            parameters={},
            skill_id=skill,
            position=Position(x=0, y=0),
        )
        assert ni.skill_id == skill


class TestNodeConfig:
    def test_create(self):
        nc = NodeConfig(
            node_id=uuid4(),
            node_type="http_request",
            name="HTTP Request",
            category="integration",
            version="1.0.0",
            input_schema={},
            output_schema={},
            parameter_schema={},
            risk_level=RiskLevel.MEDIUM,
            required_connections=["input"],
            description="Makes HTTP requests",
            is_mvp=True,
        )
        assert nc.risk_level == RiskLevel.MEDIUM


class TestWorkflowSchema:
    def _make_workflow(self):
        n1_id, n2_id = uuid4(), uuid4()
        nodes = [
            NodeInstance(
                instance_id=n1_id,
                node_id=uuid4(),
                parameters={},
                position=Position(x=0, y=0),
            ),
            NodeInstance(
                instance_id=n2_id,
                node_id=uuid4(),
                parameters={},
                position=Position(x=100, y=0),
            ),
        ]
        edge = Edge(
            from_instance_id=n1_id,
            to_instance_id=n2_id,
            from_handle="out",
            to_handle="in",
        )
        return WorkflowSchema(
            workflow_id=uuid4(),
            name="Test Workflow",
            scope="private",
            is_draft=True,
            nodes=nodes,
            connections=[edge],
        )

    def test_validate_graph_valid(self):
        wf = self._make_workflow()
        assert wf.validate_graph() is True

    def test_validate_graph_invalid_edge(self):
        wf = WorkflowSchema(
            workflow_id=uuid4(),
            name="Bad",
            scope="private",
            is_draft=True,
            nodes=[
                NodeInstance(
                    instance_id=uuid4(),
                    node_id=uuid4(),
                    parameters={},
                    position=Position(x=0, y=0),
                )
            ],
            connections=[
                Edge(
                    from_instance_id=uuid4(),
                    to_instance_id=uuid4(),
                    from_handle="out",
                    to_handle="in",
                )
            ],
        )
        assert wf.validate_graph() is False

    def test_optional_fields_default_none(self):
        wf = self._make_workflow()
        assert wf.description is None
        assert wf.version is None
        assert wf.sha256 is None
        assert wf.owner_user_id is None  # v0.3.0: Optional, 점진 마이그레이션 위해 default None

    def test_owner_user_id_accepted(self):
        owner_id = uuid4()
        wf = WorkflowSchema(
            workflow_id=uuid4(),
            owner_user_id=owner_id,
            name="Owned",
            scope="private",
            is_draft=True,
            nodes=[],
            connections=[],
        )
        assert wf.owner_user_id == owner_id
