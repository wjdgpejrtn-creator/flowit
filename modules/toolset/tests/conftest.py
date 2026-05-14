import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential, PermissionSource

from toolset.domain.entities.tool_metadata import ToolMetadata
from toolset.domain.ports.tool_registry import ToolRegistry
from toolset.domain.ports.secure_connector_port import SecureConnectorPort
from toolset.domain.ports.tool_execution_repository import ToolExecutionRepository
from toolset.domain.services.runtime_validator import RuntimeValidator
from toolset.domain.services.risk_assessment_service import RiskAssessmentService
from toolset.tests.fixtures import DummyTool, HighRiskDummyTool, RestrictedDummyTool


@pytest.fixture
def dummy_tool():
    return DummyTool()


@pytest.fixture
def high_risk_tool():
    return HighRiskDummyTool()


@pytest.fixture
def restricted_tool():
    return RestrictedDummyTool()


@pytest.fixture
def mock_credential():
    return PlaintextCredential(
        credential_id="test-cred-001",
        credential_kind="fernet",
        value="test-oauth-token",
    )


@pytest.fixture
def permission_high():
    return PermissionSource(
        user_id=uuid4(),
        role="User",
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )


@pytest.fixture
def permission_restricted():
    return PermissionSource(
        user_id=uuid4(),
        role="Admin",
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private", "Team", "Public"],
        risk_ceiling="Restricted",
    )


@pytest.fixture
def mock_tool_registry():
    registry = MagicMock(spec=ToolRegistry)
    registry.get.return_value = DummyTool()
    registry.list_all.return_value = [
        ToolMetadata.from_tool(DummyTool(), tool_id=uuid4(), category="test")
    ]
    registry.list_by_category.return_value = []
    return registry


@pytest.fixture
def mock_secure_connector():
    return AsyncMock(spec=SecureConnectorPort)


@pytest.fixture
def mock_execution_repo():
    return AsyncMock(spec=ToolExecutionRepository)


@pytest.fixture
def mock_credential_svc():
    return AsyncMock()


@pytest.fixture
def validator():
    return RuntimeValidator()


@pytest.fixture
def risk_service():
    return RiskAssessmentService()
