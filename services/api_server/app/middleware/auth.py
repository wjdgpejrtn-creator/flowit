from __future__ import annotations

from auth.adapters.middleware import AuthMiddleware as _BaseAuthMiddleware

# api_server 전용 익명 허용 경로 — 모듈 base의 `extra_public_paths` 인자로 전달.
# private `_PUBLIC_PATHS` 직접 확장보다 권장 (base 변경 시 silent break 방지).
API_SERVER_PUBLIC_PATHS: frozenset[str] = frozenset({
    "/health",
    "/api/docs",
    "/api/v1/openapi.json",
    "/api/v1/auth/authorize",
    "/api/v1/auth/callback",  # Google OAuth redirect_uri 수신
    "/api/v1/auth/refresh",   # refresh token으로 새 access 발급 — Bearer 없이 허용
})


# create_app(main.py)에서 `add_middleware(AuthMiddleware, ..., extra_public_paths=API_SERVER_PUBLIC_PATHS)`로 주입.
# 직접 subclass 없음 — base API만 사용.
AuthMiddleware = _BaseAuthMiddleware
