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
    _start = lambda: StartConnectionAuthorizeUseCase({"google": _FakeOAuth()})  # noqa: E731
    app.dependency_overrides[get_start_connection_use_case] = _start

    client = TestClient(app)
    resp = client.get("/api/v1/connections/google/authorize", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 200
    assert resp.json()["authorization_url"].startswith("https://accounts.google.com")
    assert resp.json()["state"]
    app.dependency_overrides.clear()


def test_authorize_connection_unsupported_service(app):
    app.dependency_overrides[get_current_user] = _fake_user
    _start = lambda: StartConnectionAuthorizeUseCase({"google": _FakeOAuth()})  # noqa: E731
    app.dependency_overrides[get_start_connection_use_case] = _start

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


def test_available_connections_derived_from_catalog(app):
    """GET /connections/available — 하드코딩 아닌 카탈로그 도출 + auth_type/available 정합."""
    app.dependency_overrides[get_current_user] = _fake_user

    client = TestClient(app)
    resp = client.get("/api/v1/connections/available", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 200
    by = {c["service"]: c for c in resp.json()}
    # 카탈로그 required_connections에 실재하는 provider만 노출(가짜 erp 같은 항목 없음).
    assert {"google", "slack", "linear", "anthropic", "postgresql", "mysql"} <= set(by)
    assert "erp" not in by
    # google·slack 둘 다 oauth + 배선됨(SlackOAuthClient 등록 + CONNECTION_SCOPES[slack]) → available.
    assert by["google"]["auth_type"] == "oauth" and by["google"]["available"] is True
    assert by["slack"]["auth_type"] == "oauth" and by["slack"]["available"] is True
    # api_key / connection_string provider는 키 입력이라 상시 available.
    assert by["linear"]["auth_type"] == "api_key" and by["linear"]["available"] is True
    assert by["anthropic"]["auth_type"] == "api_key"
    assert by["postgresql"]["auth_type"] == "connection_string"
    # node_count는 그 provider를 요구하는 노드 수(google은 sheets/docs/drive/gmail/calendar/bigquery 다수).
    assert by["google"]["node_count"] >= 6
    assert by["google"]["name"] == "Google Workspace"
    app.dependency_overrides.clear()


def test_available_connections_requires_auth(app):
    client = TestClient(app)
    assert client.get("/api/v1/connections/available").status_code == 401


def test_connection_providers_cover_all_catalog_providers():
    """드리프트 가드 — 카탈로그가 요구하는 모든 provider는 CONNECTION_PROVIDERS 메타가 있어야 한다.

    신규 required_connections를 가진 노드를 추가하면 메타 누락 시 available 목록에서 조용히
    빠지므로(엔드포인트가 메타 없는 provider를 skip), 이 테스트가 누락을 강제로 잡는다.
    """
    from auth.application.connection_providers import CONNECTION_PROVIDERS
    from nodes_graph.application.catalog_registry import get_all_node_definitions

    catalog_providers = {
        conn for node in get_all_node_definitions() for conn in (node.required_connections or [])
    }
    missing = catalog_providers - set(CONNECTION_PROVIDERS)
    assert not missing, f"CONNECTION_PROVIDERS 메타 누락 provider: {sorted(missing)}"


def test_connection_redirect_uri_uses_frontend_url():
    """redirect_uri = 정적 FRONTEND_URL(https) 기준 — Cloud Run 프록시 scheme(http) 어긋남 회피.

    google redirect_uri_mismatch 회귀 가드: request.url_for(프록시 뒤 http)가 아니라
    설정값 https 단일출처를 써야 한다.
    """
    from types import SimpleNamespace

    from app.routers.connections import _connection_redirect_uri

    settings = SimpleNamespace(frontend_url="https://front.example.app")
    uri = _connection_redirect_uri(None, settings, "google")  # https 분기는 request 미사용
    assert uri == "https://front.example.app/api/v1/connections/google/callback"
    assert uri.startswith("https://")  # 절대 http:// 아님


def test_connection_redirect_uri_strips_trailing_slash():
    from types import SimpleNamespace

    from app.routers.connections import _connection_redirect_uri

    settings = SimpleNamespace(frontend_url="https://front.example.app/")
    assert (
        _connection_redirect_uri(None, settings, "slack")
        == "https://front.example.app/api/v1/connections/slack/callback"
    )


def test_connection_redirect_uri_local_fallback_when_unset():
    """FRONTEND_URL 미설정(로컬 dev="/")이면 프록시가 없으므로 request.url_for 폴백."""
    from types import SimpleNamespace

    from app.routers.connections import _connection_redirect_uri

    class _Req:
        def url_for(self, name: str, **kw: str) -> str:
            return f"http://local/api/v1/connections/{kw['service']}/callback"

    settings = SimpleNamespace(frontend_url="/")
    assert (
        _connection_redirect_uri(_Req(), settings, "google")
        == "http://local/api/v1/connections/google/callback"
    )
