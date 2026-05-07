from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..domain.services.permission_resolver import PermissionResolver
from .jwt_adapter import JWTAdapter


class AuthMiddleware(BaseHTTPMiddleware):
    _PUBLIC_PATHS = {"/api/v1/auth/callback", "/api/v1/auth/login", "/healthz", "/docs", "/openapi.json"}

    def __init__(self, app, jwt_adapter: JWTAdapter, permission_resolver: PermissionResolver) -> None:
        super().__init__(app)
        self._jwt = jwt_adapter
        self._resolver = permission_resolver

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.url.path in self._PUBLIC_PATHS:
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
