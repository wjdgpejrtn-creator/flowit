from __future__ import annotations

import secrets

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from auth.adapters.oauth.google_oauth_client import GoogleOAuthClient
from auth.application.use_cases.authenticate_use_case import AuthenticateUseCase
from auth.application.use_cases.refresh_token_use_case import RefreshTokenUseCase
from auth.domain.value_objects.token_pair import TokenPair
from common_schemas import PermissionSource

from app.dependencies.auth import (
    get_authenticate_use_case,
    get_google_oauth,
    get_refresh_token_use_case,
)
from app.dependencies.permission import get_permission_source

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AuthorizeResponse(BaseModel):
    authorization_url: str
    state: str


@router.get("/authorize", response_model=AuthorizeResponse)
async def authorize(
    google_oauth: GoogleOAuthClient = Depends(get_google_oauth),
) -> AuthorizeResponse:
    state = secrets.token_urlsafe(24)
    url = google_oauth.authorization_url(state)
    return AuthorizeResponse(authorization_url=url, state=state)


@router.post("/login", response_model=TokenPair)
async def login(
    req: LoginRequest = Body(...),
    use_case: AuthenticateUseCase = Depends(get_authenticate_use_case),
) -> TokenPair:
    try:
        return await use_case.execute(req.code)
    except Exception as exc:
        # Google OAuth 실패(invalid code) 등은 401로 표면화
        raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}") from exc


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    req: RefreshRequest = Body(...),
    use_case: RefreshTokenUseCase = Depends(get_refresh_token_use_case),
) -> TokenPair:
    return await use_case.execute(req.refresh_token)


@router.get("/me", response_model=PermissionSource)
async def me(
    permission: PermissionSource = Depends(get_permission_source),
) -> PermissionSource:
    return permission
