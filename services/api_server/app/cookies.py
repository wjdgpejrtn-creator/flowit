from __future__ import annotations

from auth.domain.value_objects.token_pair import TokenPair
from fastapi import Response

from app.config import Settings

# ADR-0021 — 단일 출처 토폴로지의 HttpOnly 쿠키 인증.
# 쿠키 이름은 modules/auth AuthMiddleware의 토큰 추출과 계약상 일치해야 한다.
ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"

# refresh_token TTL = access TTL * 7 — AuthenticateUseCase / RefreshTokenUseCase 계약과 동일.
REFRESH_TTL_MULTIPLIER = 7


def _secure(settings: Settings) -> bool:
    # dev는 http://localhost 라 Secure 쿠키가 전송되지 않을 수 있음 → staging/production만 Secure.
    return settings.environment != "dev"


def set_auth_cookies(response: Response, tokens: TokenPair, settings: Settings) -> None:
    """access/refresh 토큰을 HttpOnly 쿠키로 굽는다. 단일 출처라 Domain 속성은 불필요."""
    secure = _secure(settings)
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access_token,
        max_age=tokens.expires_in,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=tokens.expires_in * REFRESH_TTL_MULTIPLIER,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    """로그아웃 시 인증 쿠키 제거. set 시점과 path/secure/samesite가 일치해야 브라우저가 삭제한다."""
    secure = _secure(settings)
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(
            name,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
        )
