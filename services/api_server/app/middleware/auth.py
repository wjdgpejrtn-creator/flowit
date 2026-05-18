from __future__ import annotations

from auth.adapters.middleware import AuthMiddleware as _BaseAuthMiddleware


class AuthMiddleware(_BaseAuthMiddleware):
    """REQ-009: modules/auth AuthMiddleware 확장.

    `/health` (DB+Redis+Orchestrator 3-way 연결성)를 익명 허용 경로에 추가.
    base는 `/healthz`만 허용하므로 service-local subclass로 확장한다.
    """

    _PUBLIC_PATHS = _BaseAuthMiddleware._PUBLIC_PATHS | {
        "/health",
        "/api/docs",
        "/api/v1/openapi.json",
        "/api/v1/auth/authorize",
        "/api/v1/auth/refresh",  # refresh token으로 새 access 발급 — Bearer 없이도 허용
    }
