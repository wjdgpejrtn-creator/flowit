from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..domain.services.permission_resolver import PermissionResolver
from .jwt_adapter import JWTAdapter


class AuthMiddleware(BaseHTTPMiddleware):
    # 기본 익명 허용 경로. service-local 확장은 __init__의 `extra_public_paths` 인자 사용
    # (private `_PUBLIC_PATHS` 직접 확장보다 권장 — base 변경 시 silent break 방지).
    _PUBLIC_PATHS = frozenset({"/api/v1/auth/callback", "/api/v1/auth/login", "/healthz", "/docs", "/openapi.json"})

    def __init__(
        self,
        app,
        jwt_adapter: JWTAdapter,
        permission_resolver: PermissionResolver,
        extra_public_paths: frozenset[str] | set[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._jwt = jwt_adapter
        self._resolver = permission_resolver
        self._public_paths: frozenset[str] = (
            self._PUBLIC_PATHS | frozenset(extra_public_paths) if extra_public_paths else self._PUBLIC_PATHS
        )

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.url.path in self._public_paths:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"code": "E-AUTH-003", "message": "Missing token"}, status_code=401)

        token = auth_header.removeprefix("Bearer ")

        try:
            payload = self._jwt.decode(token)
        except Exception:
            return JSONResponse({"code": "E-AUTH-003", "message": "Invalid or expired token"}, status_code=401)

        if payload.get("type") != "access":
            return JSONResponse({"code": "E-AUTH-003", "message": "Not an access token"}, status_code=401)

        # Attach minimal permission context; full PermissionSource is assembled in DI layer
        request.state.user_id = uuid.UUID(payload["sub"])
        request.state.session_hash = payload.get("session_hash", "")

        return await call_next(request)
