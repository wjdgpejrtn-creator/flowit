from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OAuthClientPort(ABC):
    @abstractmethod
    def authorization_url(
        self, state: str, scopes: list[str] | None = None, redirect_uri: str | None = None
    ) -> str:
        """OAuth authorization URL. scopes 미지정 시 로그인 신원 scope, 지정 시 connection scope (ADR-0027).

        redirect_uri 미지정 시 기본(로그인 callback). connection은 자신의 callback 경로를 전달해야
        google이 connection callback으로 redirect한다(authorize·exchange_code 일치 필수).
        """
        ...

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> dict[str, Any]: ...

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]: ...

    @abstractmethod
    async def get_user_info(self, access_token: str) -> dict[str, Any]: ...
