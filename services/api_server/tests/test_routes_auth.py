from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies.auth import (
    get_authenticate_use_case,
    get_google_oauth,
    get_refresh_token_use_case,
    get_session_repository,
    get_user_repository,
)
from app.main import create_app
from auth.domain.entities.session import Session
from auth.domain.entities.user import User
from auth.domain.value_objects.token_pair import TokenPair


@pytest.fixture
def app(env_minimum: None):
    settings = Settings()  # type: ignore[call-arg]
    return create_app(settings)


def test_authorize_returns_url(app, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_oauth = MagicMock()
    fake_oauth.authorization_url.return_value = "https://accounts.google.com/o/oauth2/v2/auth?fake"
    app.dependency_overrides[get_google_oauth] = lambda: fake_oauth

    client = TestClient(app)
    resp = client.get("/api/v1/auth/authorize")

    assert resp.status_code == 200
    body = resp.json()
    assert body["authorization_url"].startswith("https://accounts.google.com")
    assert len(body["state"]) > 16

    app.dependency_overrides.clear()


def test_login_exchanges_code_for_token_pair(app) -> None:
    fake_uc = MagicMock()
    fake_uc.execute = AsyncMock(
        return_value=TokenPair(access_token="acc.jwt", refresh_token="ref.jwt", expires_in=3600)
    )
    app.dependency_overrides[get_authenticate_use_case] = lambda: fake_uc

    client = TestClient(app)
    resp = client.post("/api/v1/auth/login", json={"code": "google-auth-code"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] == "acc.jwt"
    assert body["refresh_token"] == "ref.jwt"
    assert body["token_type"] == "Bearer"
    fake_uc.execute.assert_awaited_once_with("google-auth-code")

    app.dependency_overrides.clear()


def test_login_failure_returns_401(app) -> None:
    fake_uc = MagicMock()
    fake_uc.execute = AsyncMock(side_effect=Exception("invalid code"))
    app.dependency_overrides[get_authenticate_use_case] = lambda: fake_uc

    client = TestClient(app)
    resp = client.post("/api/v1/auth/login", json={"code": "bad"})

    assert resp.status_code == 401
    app.dependency_overrides.clear()


def test_refresh_returns_new_pair(app) -> None:
    fake_uc = MagicMock()
    fake_uc.execute = AsyncMock(
        return_value=TokenPair(access_token="new-acc", refresh_token="new-ref", expires_in=3600)
    )
    app.dependency_overrides[get_refresh_token_use_case] = lambda: fake_uc

    client = TestClient(app)
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "ref.jwt"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] == "new-acc"
    fake_uc.execute.assert_awaited_once_with("ref.jwt")

    app.dependency_overrides.clear()


def test_me_returns_permission_source_for_authenticated_user(app) -> None:
    # AuthMiddleware는 JWT 검증 — 실제 토큰 사용. JWT_SECRET_KEY는 env_minimum에서
    # 미설정이라 빈 secret으로 encode → AuthMiddleware도 같은 secret으로 decode 가능.
    import jwt as pyjwt

    user_id = uuid4()
    dept_id = uuid4()
    session_hash = "test-session-hash"
    now = datetime.now(UTC)

    access_token = pyjwt.encode(
        {
            "sub": str(user_id),
            "session_hash": session_hash,
            "type": "access",
            "exp": now + timedelta(seconds=3600),
            "iat": now,
        },
        "",
        algorithm="HS256",
    )

    fake_user_repo = MagicMock()
    fake_user_repo.find_by_id = AsyncMock(
        return_value=User(
            user_id=user_id,
            email="alice@example.com",
            name="Alice",
            role="Admin",
            department_id=dept_id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )

    fake_session_repo = MagicMock()
    fake_session_repo.find_by_hash = AsyncMock(
        return_value=Session(
            session_id=uuid4(),
            user_id=user_id,
            session_hash=session_hash,
            expires_at=now + timedelta(hours=1),
            is_revoked=False,
            created_at=now,
        )
    )

    app.dependency_overrides[get_user_repository] = lambda: fake_user_repo
    app.dependency_overrides[get_session_repository] = lambda: fake_session_repo

    client = TestClient(app)
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == str(user_id)
    assert body["role"] == "Admin"
    assert body["department_id"] == str(dept_id)
    assert body["risk_ceiling"] == "Restricted"  # Admin
    assert "Public" in body["granted_scopes"]

    app.dependency_overrides.clear()


def test_me_without_bearer_returns_401(app) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_authorize_is_public(app, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_oauth = MagicMock()
    fake_oauth.authorization_url.return_value = "https://accounts.google.com/o"
    app.dependency_overrides[get_google_oauth] = lambda: fake_oauth

    client = TestClient(app)
    resp = client.get("/api/v1/auth/authorize")
    assert resp.status_code == 200  # Bearer 없이도 통과

    app.dependency_overrides.clear()
