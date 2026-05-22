from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.config import Settings
from app.dependencies.auth import (
    get_authenticate_use_case,
    get_google_oauth,
    get_jwt_adapter,
    get_refresh_token_use_case,
    get_session_repository,
    get_user_repository,
)
from app.main import create_app
from auth.domain.entities.session import Session
from auth.domain.entities.user import User
from auth.domain.value_objects.token_pair import TokenPair
from common_schemas.exceptions import AuthorizationError
from fastapi.testclient import TestClient


@pytest.fixture
def app(env_minimum: None):
    settings = Settings()  # type: ignore[call-arg]
    return create_app(settings)


def _set_cookie_header(resp) -> str:
    """Set-Cookie 헤더 전체를 단일 문자열로 — 속성 검사용."""
    return " | ".join(resp.headers.get_list("set-cookie"))


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


def test_callback_sets_cookies_and_redirects(app) -> None:
    """ADR-0021 — callback은 토큰을 JSON이 아닌 HttpOnly 쿠키로 굽고 frontend로 302."""
    fake_uc = MagicMock()
    fake_uc.execute = AsyncMock(
        return_value=TokenPair(access_token="acc.jwt", refresh_token="ref.jwt", expires_in=3600)
    )
    app.dependency_overrides[get_authenticate_use_case] = lambda: fake_uc

    client = TestClient(app)
    # Redis 미설정(dev) → state 검증 skip. follow_redirects=False로 302 자체를 검사.
    resp = client.get("/api/v1/auth/callback?code=google-auth-code&state=s", follow_redirects=False)

    assert resp.status_code == 302
    cookies = _set_cookie_header(resp)
    assert "access_token=acc.jwt" in cookies
    assert "refresh_token=ref.jwt" in cookies
    assert "HttpOnly" in cookies
    assert "SameSite=lax" in cookies
    # 토큰이 응답 본문(JSON)으로 노출되지 않아야 함
    assert "acc.jwt" not in resp.text

    app.dependency_overrides.clear()


def test_refresh_from_cookie_returns_new_cookies(app) -> None:
    """ADR-0021 — refresh는 쿠키에서 refresh_token을 읽고 새 쿠키를 재set."""
    fake_uc = MagicMock()
    fake_uc.execute = AsyncMock(
        return_value=TokenPair(access_token="new-acc", refresh_token="new-ref", expires_in=3600)
    )
    app.dependency_overrides[get_refresh_token_use_case] = lambda: fake_uc

    client = TestClient(app)
    client.cookies.set("refresh_token", "ref.jwt")
    resp = client.post("/api/v1/auth/refresh")

    assert resp.status_code == 200
    assert resp.json()["expires_in"] == 3600
    cookies = _set_cookie_header(resp)
    assert "access_token=new-acc" in cookies
    assert "refresh_token=new-ref" in cookies
    fake_uc.execute.assert_awaited_once_with("ref.jwt")

    app.dependency_overrides.clear()


def test_refresh_without_cookie_returns_401(app) -> None:
    # /refresh는 public path라 핸들러 진입 전 use case 의존성이 resolve된다 → fake로 차단.
    app.dependency_overrides[get_refresh_token_use_case] = lambda: MagicMock()

    client = TestClient(app)
    resp = client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401

    app.dependency_overrides.clear()


def test_refresh_with_invalid_token_returns_401(app) -> None:
    """만료·무효 refresh 토큰 = 재인증 필요한 정상 케이스 → 500/403이 아닌 401."""
    fake_uc = MagicMock()
    fake_uc.execute = AsyncMock(side_effect=AuthorizationError("Session expired", code="E-AUTH-006"))
    app.dependency_overrides[get_refresh_token_use_case] = lambda: fake_uc

    client = TestClient(app)
    client.cookies.set("refresh_token", "expired.jwt")
    resp = client.post("/api/v1/auth/refresh")

    assert resp.status_code == 401

    app.dependency_overrides.clear()


def test_logout_revokes_session_and_clears_cookies(app) -> None:
    """ADR-0021 — logout은 세션을 revoke하고 인증 쿠키를 제거."""
    session_id = uuid4()
    fake_jwt = MagicMock()
    fake_jwt.decode.return_value = {"session_hash": "sess-hash", "type": "refresh"}

    fake_session_repo = MagicMock()
    fake_session_repo.find_by_hash = AsyncMock(
        return_value=Session(
            session_id=session_id,
            user_id=uuid4(),
            session_hash="sess-hash",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            is_revoked=False,
            created_at=datetime.now(UTC),
        )
    )
    fake_session_repo.revoke = AsyncMock()

    app.dependency_overrides[get_jwt_adapter] = lambda: fake_jwt
    app.dependency_overrides[get_session_repository] = lambda: fake_session_repo

    client = TestClient(app)
    client.cookies.set("refresh_token", "ref.jwt")
    resp = client.post("/api/v1/auth/logout")

    assert resp.status_code == 204
    fake_session_repo.revoke.assert_awaited_once_with(session_id)
    cookies = _set_cookie_header(resp)
    assert "access_token=" in cookies
    assert "refresh_token=" in cookies
    assert 'Max-Age=0' in cookies or "expires=Thu, 01 Jan 1970" in cookies.lower()

    app.dependency_overrides.clear()


def test_logout_without_cookie_still_succeeds(app) -> None:
    """토큰 쿠키가 없어도 로그아웃은 성공 (쿠키만 정리)."""
    # /logout은 public path라 핸들러 진입 전 session repo 의존성이 resolve된다 → fake로 차단.
    app.dependency_overrides[get_session_repository] = lambda: MagicMock()

    client = TestClient(app)
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 204

    app.dependency_overrides.clear()


def _authenticated_repos(user_id, dept_id, session_hash: str):
    now = datetime.now(UTC)
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
    return fake_user_repo, fake_session_repo


def _access_token(user_id, session_hash: str) -> str:
    import jwt as pyjwt

    now = datetime.now(UTC)
    return pyjwt.encode(
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


def test_me_returns_permission_source_for_authenticated_user(app) -> None:
    # AuthMiddleware는 JWT 검증 — 실제 토큰 사용. JWT_SECRET_KEY는 env_minimum에서
    # 미설정이라 빈 secret으로 encode → AuthMiddleware도 같은 secret으로 decode 가능.
    user_id = uuid4()
    dept_id = uuid4()
    session_hash = "test-session-hash"
    access_token = _access_token(user_id, session_hash)
    fake_user_repo, fake_session_repo = _authenticated_repos(user_id, dept_id, session_hash)

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


def test_me_authenticates_via_access_token_cookie(app) -> None:
    """ADR-0021 — Authorization 헤더 없이 access_token 쿠키만으로 인증."""
    user_id = uuid4()
    dept_id = uuid4()
    session_hash = "cookie-session-hash"
    access_token = _access_token(user_id, session_hash)
    fake_user_repo, fake_session_repo = _authenticated_repos(user_id, dept_id, session_hash)

    app.dependency_overrides[get_user_repository] = lambda: fake_user_repo
    app.dependency_overrides[get_session_repository] = lambda: fake_session_repo

    client = TestClient(app)
    client.cookies.set("access_token", access_token)
    resp = client.get("/api/v1/auth/me")  # 헤더 없음

    assert resp.status_code == 200
    assert resp.json()["user_id"] == str(user_id)

    app.dependency_overrides.clear()


def test_me_without_credentials_returns_401(app) -> None:
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
