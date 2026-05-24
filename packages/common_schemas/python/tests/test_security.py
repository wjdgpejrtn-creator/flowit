from uuid import uuid4

import pytest
from pydantic import ValidationError

from common_schemas.security import PermissionSource, PlaintextCredential, UserRole


class TestPermissionSource:
    def test_create(self):
        ps = PermissionSource(
            user_id=uuid4(),
            role="Admin",
            department_id=uuid4(),
            session_id=uuid4(),
            granted_scopes=["Private", "Team"],
            risk_ceiling="High",
        )
        assert ps.role == "Admin"
        assert len(ps.granted_scopes) == 2

    def test_manager_roles_accepted(self):
        for role in ("team_manager", "company_manager"):
            ps = PermissionSource(
                user_id=uuid4(),
                role=role,
                department_id=uuid4(),
                session_id=uuid4(),
                granted_scopes=["Private"],
                risk_ceiling="High",
            )
            assert ps.role == role

    def test_invalid_role(self):
        with pytest.raises(ValidationError):
            PermissionSource(
                user_id=uuid4(),
                role="SuperAdmin",
                department_id=uuid4(),
                session_id=uuid4(),
                granted_scopes=["Private"],
                risk_ceiling="High",
            )

    def test_frozen(self):
        ps = PermissionSource(
            user_id=uuid4(),
            role="User",
            department_id=uuid4(),
            session_id=uuid4(),
            granted_scopes=["Private"],
            risk_ceiling="Restricted",
        )
        with pytest.raises(ValidationError):
            ps.role = "Admin"


class TestUserRole:
    def test_literal_members(self):
        """SSOT: auth UserRole · PermissionSource.role · DB 021 CHECK가 공유하는 4종."""
        assert set(UserRole.__args__) == {"User", "team_manager", "company_manager", "Admin"}


class TestPlaintextCredential:
    def test_create(self):
        pc = PlaintextCredential(
            credential_id="cred_001",
            credential_kind="fernet",
            value="secret_key_data",
        )
        assert pc.value == "secret_key_data"

    def test_wipe(self):
        pc = PlaintextCredential(
            credential_id="cred_002",
            credential_kind="aes_gcm",
            value="sensitive_data",
        )
        pc.wipe()
        assert pc.value == ""

    def test_mutable(self):
        pc = PlaintextCredential(
            credential_id="cred_003",
            credential_kind="fernet",
            value="data",
        )
        pc.value = "new_data"
        assert pc.value == "new_data"
