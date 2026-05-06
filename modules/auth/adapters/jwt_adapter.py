from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as pyjwt


class JWTAdapter:
    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str | None = None,
    ) -> None:
        self._secret = secret_key or os.getenv("JWT_SECRET_KEY", "")
        self._algorithm = algorithm or os.getenv("JWT_ALGORITHM", "HS256")

    def encode(self, payload: dict[str, Any], ttl_seconds: int | None = None) -> str:
        expiry = ttl_seconds or int(os.getenv("JWT_EXPIRY_SECONDS", "3600"))
        data = {
            **payload,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(seconds=expiry),
        }
        return pyjwt.encode(data, self._secret, algorithm=self._algorithm)

    def decode(self, token: str) -> dict[str, Any]:
        return pyjwt.decode(token, self._secret, algorithms=[self._algorithm])
