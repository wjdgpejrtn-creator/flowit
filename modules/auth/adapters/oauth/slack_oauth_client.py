from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import httpx

from ...domain.ports.oauth_client_port import OAuthClientPort

_AUTH_URL = "https://slack.com/oauth/v2/authorize"
_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
_AUTH_TEST_URL = "https://slack.com/api/auth.test"
_TIMEOUT_SECONDS = 30


class SlackOAuthError(RuntimeError):
    """slack API가 HTTP 200 + {"ok": false, "error": ...}로 반환한 논리 오류."""


class SlackOAuthClient(OAuthClientPort):
    """Slack OAuth 2.0 (v2) 클라이언트 — bot 토큰(xoxb-) 설치 흐름 (REQ-002).

    google과 다른 점:
    - 토큰 엔드포인트(`oauth.v2.access`)는 실패도 **HTTP 200 + `{"ok": false, "error": ...}`**로
      반환한다 → `raise_for_status`로는 못 잡으므로 `ok` 필드를 명시 확인한다.
    - bot 토큰은 응답 최상위 `access_token`(xoxb-), 계정 식별자는 `team.id`/`team.name`.
    - scope는 **콤마 구분**(google은 공백).

    `transport`는 테스트 주입 seam(httpx.MockTransport). 운영은 None(기본 transport).
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client_id = client_id or os.getenv("SLACK_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("SLACK_CLIENT_SECRET", "")
        self._redirect_uri = redirect_uri or os.getenv("SLACK_REDIRECT_URI", "")
        self._transport = transport

    def authorization_url(
        self, state: str, scopes: list[str] | None = None, redirect_uri: str | None = None
    ) -> str:
        """slack v2 authorize URL. bot scope는 `scope`에 콤마 구분으로 전달한다."""
        params = {
            "client_id": self._client_id,
            "scope": ",".join(scopes or []),
            "redirect_uri": redirect_uri or self._redirect_uri,
            "state": state,
        }
        return f"{_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> dict[str, Any]:
        uri = redirect_uri or self._redirect_uri
        async with httpx.AsyncClient(transport=self._transport, timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": uri,
                },
            )
            resp.raise_for_status()
            tokens: dict = resp.json()

        if not tokens.get("ok", False):
            raise SlackOAuthError(f"Slack oauth.v2.access failed: {tokens.get('error', 'unknown')}")

        team = tokens.get("team", {}) or {}
        return {
            "access_token": tokens["access_token"],          # xoxb- bot 토큰
            "refresh_token": tokens.get("refresh_token", ""),  # token rotation 활성 시에만
            "expires_in": tokens.get("expires_in"),            # rotation 비활성 bot 토큰은 무만료(None)
            "scopes": [s for s in tokens.get("scope", "").split(",") if s],  # 콤마 구분
            "account_id": team.get("id"),                      # team_id (안정 식별자)
            "display_name": team.get("name"),                  # workspace 이름
        }

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(transport=self._transport, timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            resp.raise_for_status()
            tokens: dict = resp.json()

        if not tokens.get("ok", False):
            raise SlackOAuthError(f"Slack token refresh failed: {tokens.get('error', 'unknown')}")
        return tokens

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(transport=self._transport, timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                _AUTH_TEST_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            info: dict = resp.json()
        if not info.get("ok", False):
            raise SlackOAuthError(f"Slack auth.test failed: {info.get('error', 'unknown')}")
        return info
