from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt as pyjwt
import pytest
from app.config import Settings
from app.dependencies.auth import get_oauth_repository
from app.dependencies.permission import get_current_user
from app.main import create_app
from auth.domain.entities.oauth_connection import OAuthConnection
from auth.domain.entities.user import User
from auth.domain.ports.oauth_connection_repository import OAuthConnectionRepository
from fastapi.testclient import TestClient

USER_ID = uuid4()


@pytest.fixture
def app(env_minimum: None):
    return create_app(Settings())  # type: ignore[call-arg]


def _bearer() -> str:
    now = datetime.now(UTC)
    return pyjwt.encode(
        {
            "sub": str(USER_ID),
            "session_hash": "dummy-hash",
            "type": "access",
            "exp": now + timedelta(seconds=3600),
            "iat": now,
        },
        "test-jwt-secret-key-min-32-bytes",
        algorithm="HS256",
    )


def _fake_user() -> User:
    now = datetime.now(UTC)
    return User(
        user_id=USER_ID, email="u@x.com", name="U", role="User",
        department_id=None, is_active=True, created_at=now, updated_at=now,
    )


def _conn(service: str, display: str | None) -> OAuthConnection:
    return OAuthConnection(
        oauth_id=uuid4(), user_id=USER_ID, service=service, credential_id=uuid4(),
        access_token_encrypted=b"x", refresh_token_encrypted=None, scopes=[],
        is_active=True, connected_at=datetime.now(UTC), account_id="acc", display_name=display,
    )


def test_list_connections_returns_active(app):
    repo = AsyncMock(spec=OAuthConnectionRepository)
    repo.list_for_user = AsyncMock(return_value=[_conn("google", "u@x.com"), _conn("slack", "flowit-team")])
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_oauth_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get("/api/v1/connections", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 200
    body = {c["service"]: c for c in resp.json()}
    assert body["google"]["display"] == "u@x.com"
    assert body["google"]["connected"] is True
    assert body["google"]["status"] == "connected"
    assert body["slack"]["display"] == "flowit-team"
    app.dependency_overrides.clear()


def test_list_connections_empty(app):
    repo = AsyncMock(spec=OAuthConnectionRepository)
    repo.list_for_user = AsyncMock(return_value=[])
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_oauth_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get("/api/v1/connections", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 200
    assert resp.json() == []
    app.dependency_overrides.clear()


def test_list_connections_requires_auth(app):
    """AuthMiddleware — Bearer 없으면 401 (가짜 '연결됨' 우회 방지)."""
    client = TestClient(app)
    resp = client.get("/api/v1/connections")
    assert resp.status_code == 401
