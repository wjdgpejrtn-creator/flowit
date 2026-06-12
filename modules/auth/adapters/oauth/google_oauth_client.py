from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import httpx

from ...domain.ports.oauth_client_port import OAuthClientPort

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# 로그인 전용 — 신원(identity) scope만. 서비스 연동(Sheets/Drive/Docs/Calendar/Gmail) scope는
# connection authorize 플로우(ADR-0027)에서 scope 인자로 별도 요청한다. 로그인 access_token을
# drive/gmail API로 쓰는 소비처는 0건이라 트림해도 기존 기능 무영향(2026-06-08 조장 확인).
_DEFAULT_SCOPES = [
    "openid",
    "email",
    "profile",
]


class GoogleOAuthClient(OAuthClientPort):
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        self._client_id = client_id or os.getenv("GOOGLE_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET", "")
        self._redirect_uri = redirect_uri or os.getenv("GOOGLE_REDIRECT_URI", "")

    def authorization_url(
        self, state: str, scopes: list[str] | None = None, redirect_uri: str | None = None
    ) -> str:
        """OAuth authorization URL 생성.

        scopes 미지정 시 로그인 신원 scope(`_DEFAULT_SCOPES`). connection authorize는
        서비스 scope(Sheets/Drive 등)를 scopes로 전달한다(ADR-0027 ② scope 분리).
        redirect_uri 미지정 시 기본(로그인 callback). connection은 자신의 callback 경로를 전달해
        google이 connection callback으로 돌려보내게 한다(exchange_code와 동일 값 필수 — google 검증).
        include_granted_scopes=true로 incremental authorization — 기존 승인 scope를 누적한다.
        """
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri or self._redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes or _DEFAULT_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"{_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> dict[str, Any]:
        uri = redirect_uri or self._redirect_uri
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": uri,
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            tokens: dict = token_resp.json()

        userinfo = await self.get_user_info(tokens["access_token"])
        return {
            "sub": userinfo["sub"],
            "email": userinfo.get("email", ""),
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token", ""),
            # #452 ② access token 만료시각 계산용(초). google은 통상 3599. 미수신 시 None.
            "expires_in": tokens.get("expires_in"),
            "scopes": tokens.get("scope", "").split(),
        }

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()
