import pytest
from uuid import uuid4
from common_schemas.security import PlaintextCredential, PermissionSource

from toolset.tests.fixtures import DummyTool, HighRiskDummyTool


@pytest.fixture
def dummy_tool():
    return DummyTool()


@pytest.fixture
def high_risk_tool():
    return HighRiskDummyTool()


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
def permission_low():
    return PermissionSource(
        user_id=uuid4(),
        role="User",
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="Low",
    )
