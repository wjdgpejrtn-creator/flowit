from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OAuthClientPort(ABC):
    @abstractmethod
    async def exchange_code(self, code: str) -> dict[str, Any]: ...

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]: ...

    @abstractmethod
    async def get_user_info(self, access_token: str) -> dict[str, Any]: ...
