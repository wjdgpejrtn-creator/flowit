"""SlackOAuthClient (OAuthClientPort) 단위 테스트 — slack OAuth v2 (REQ-002).

slack은 google과 응답 구조가 다르다:
- oauth.v2.access는 실패도 HTTP 200 + {"ok": false, "error": ...}로 반환 → ok 체크 필수
- bot 토큰은 resp["access_token"](xoxb-), 계정 식별자는 resp["team"]["id"]/["name"]
- scope는 콤마 구분(google은 공백)

HTTP 호출은 httpx.MockTransport로 차단(respx 미설치).
"""
from __future__ import annotations

import httpx
import pytest
from auth.adapters.oauth.slack_oauth_client import SlackOAuthClient


def _transport(handler):
    return httpx.MockTransport(handler)


def _client(handler=None, **kw):
    return SlackOAuthClient(
        client_id="cid",
        client_secret="csec",
        redirect_uri="https://app/api/v1/connections/slack/callback",
        transport=_transport(handler) if handler else None,
        **kw,
    )


# ── authorization_url (순수, 네트워크 없음) ───────────────────────────────────


def test_authorization_url_builds_slack_v2():
    url = _client().authorization_url(
        "state123",
        scopes=["chat:write", "channels:history"],
        redirect_uri="https://app/api/v1/connections/slack/callback",
    )
    assert url.startswith("https://slack.com/oauth/v2/authorize?")
    assert "client_id=cid" in url
    assert "state=state123" in url
    # slack bot scope는 콤마 구분(urlencode되면 %2C) → 디코드해서 확인
    decoded = url.replace("%3A", ":").replace("%2C", ",")
    assert "chat:write,channels:history" in decoded
    assert "redirect_uri=" in url


# ── exchange_code ─────────────────────────────────────────────────────────────


def _oauth_access_ok(request: httpx.Request) -> httpx.Response:
    assert "oauth.v2.access" in str(request.url)
    return httpx.Response(
        200,
        json={
            "ok": True,
            "access_token": "xoxb-demo-token",
            "token_type": "bot",
            "scope": "chat:write,channels:history",
            "bot_user_id": "B123",
            "team": {"id": "T0ABC", "name": "FlowIt Workspace"},
            "authed_user": {"id": "U999"},
        },
    )


@pytest.mark.asyncio
async def test_exchange_code_maps_bot_token_and_team():
    client = _client(_oauth_access_ok)
    info = await client.exchange_code("code1", "https://app/api/v1/connections/slack/callback")

    assert info["access_token"] == "xoxb-demo-token"  # 봇 토큰
    assert info["account_id"] == "T0ABC"              # team_id
    assert info["display_name"] == "FlowIt Workspace"  # workspace 이름
    assert info["scopes"] == ["chat:write", "channels:history"]  # 콤마 분리


@pytest.mark.asyncio
async def test_exchange_code_raises_on_ok_false():
    """slack은 실패도 HTTP 200 + ok:false → 명시적 예외."""
    def handler(request):
        return httpx.Response(200, json={"ok": False, "error": "invalid_code"})

    client = _client(handler)
    with pytest.raises(Exception) as exc:
        await client.exchange_code("bad", "https://app/cb")
    assert "invalid_code" in str(exc.value)


# ── refresh_access_token (token rotation) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_access_token_returns_new_token():
    def handler(request):
        body = bytes(request.content).decode()
        assert "grant_type=refresh_token" in body
        return httpx.Response(
            200,
            json={"ok": True, "access_token": "xoxb-new", "expires_in": 43200, "refresh_token": "xoxe-new"},
        )

    client = _client(handler)
    resp = await client.refresh_access_token("xoxe-old")
    assert resp["access_token"] == "xoxb-new"
    assert resp["expires_in"] == 43200


@pytest.mark.asyncio
async def test_refresh_raises_on_ok_false():
    def handler(request):
        return httpx.Response(200, json={"ok": False, "error": "invalid_refresh_token"})

    client = _client(handler)
    with pytest.raises(Exception):
        await client.refresh_access_token("bad")


# ── get_user_info (auth.test) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_user_info_returns_team():
    def handler(request):
        assert "auth.test" in str(request.url)
        return httpx.Response(200, json={"ok": True, "team_id": "T0ABC", "team": "FlowIt", "user_id": "U999"})

    client = _client(handler)
    info = await client.get_user_info("xoxb-demo-token")
    assert info["team_id"] == "T0ABC"
