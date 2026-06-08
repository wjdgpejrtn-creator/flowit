from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt as pyjwt
import pytest
from app.config import Settings
from app.dependencies.connections import (
    get_list_connections_use_case,
    get_revoke_connection_use_case,
    get_start_connection_use_case,
)
from app.dependencies.permission import get_current_user
from app.main import create_app
from auth.application.use_cases.list_connections_use_case import ListConnectionsUseCase
from auth.application.use_cases.revoke_connection_use_case import RevokeConnectionUseCase
from auth.application.use_cases.start_connection_authorize_use_case import StartConnectionAuthorizeUseCase
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
        {"sub": str(USER_ID), "session_hash": "h", "type": "access",
         "exp": now + timedelta(seconds=3600), "iat": now},
        "test-jwt-secret-key-min-32-bytes", algorithm="HS256",
    )


def _fake_user() -> User:
    now = datetime.now(UTC)
    return User(user_id=USER_ID, email="u@x.com", name="U", role="User",
                department_id=None, is_active=True, created_at=now, updated_at=now)


def _conn(service: str, display: str | None) -> OAuthConnection:
    return OAuthConnection(
        oauth_id=uuid4(), user_id=USER_ID, service=service, credential_id=uuid4(),
        access_token_encrypted=b"x", refresh_token_encrypted=None, scopes=[],
        is_active=True, connected_at=datetime.now(UTC), account_id="acc", display_name=display,
    )


class _FakeOAuth:
    def authorization_url(self, state: str, scopes=None, redirect_uri=None) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"

    async def exchange_code(self, code: str, redirect_uri=None) -> dict:
        return {"sub": "s", "email": "u@x.com", "access_token": "t", "refresh_token": "r", "scopes": []}


def _list_uc(*conns: OAuthConnection) -> ListConnectionsUseCase:
    repo = AsyncMock(spec=OAuthConnectionRepository)
    repo.list_for_user = AsyncMock(return_value=list(conns))
    return ListConnectionsUseCase(repo)


def test_list_connections_returns_active(app):
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_list_connections_use_case] = lambda: _list_uc(
        _conn("google", "u@x.com"), _conn("slack", "flowit-team")
    )

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
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_list_connections_use_case] = lambda: _list_uc()

    client = TestClient(app)
    resp = client.get("/api/v1/connections", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 200
    assert resp.json() == []
    app.dependency_overrides.clear()


def test_list_connections_requires_auth(app):
    """AuthMiddleware — Bearer 없으면 401."""
    client = TestClient(app)
    assert client.get("/api/v1/connections").status_code == 401


def test_authorize_connection_returns_url(app):
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_start_connection_use_case] = lambda: StartConnectionAuthorizeUseCase(_FakeOAuth())

    client = TestClient(app)
    resp = client.get("/api/v1/connections/google/authorize", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 200
    assert resp.json()["authorization_url"].startswith("https://accounts.google.com")
    assert resp.json()["state"]
    app.dependency_overrides.clear()


def test_authorize_connection_unsupported_service(app):
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_start_connection_use_case] = lambda: StartConnectionAuthorizeUseCase(_FakeOAuth())

    client = TestClient(app)
    resp = client.get("/api/v1/connections/notion/authorize", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 400
    app.dependency_overrides.clear()


def test_revoke_connection(app):
    repo = AsyncMock(spec=OAuthConnectionRepository)
    repo.get_active_for_user = AsyncMock(return_value=_conn("google", "u@x.com"))
    repo.revoke = AsyncMock()
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_revoke_connection_use_case] = lambda: RevokeConnectionUseCase(repo)

    client = TestClient(app)
    resp = client.delete("/api/v1/connections/google", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 200
    assert resp.json() == {"service": "google", "revoked": True}
    repo.revoke.assert_awaited_once()
    app.dependency_overrides.clear()
