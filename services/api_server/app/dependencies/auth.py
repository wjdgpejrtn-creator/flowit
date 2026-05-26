from __future__ import annotations

from functools import lru_cache

from auth.adapters.cipher.aes_gcm import AESGCMCipher
from auth.adapters.jwt_adapter import JWTAdapter
from auth.adapters.oauth.google_oauth_client import GoogleOAuthClient
from auth.application.use_cases.authenticate_use_case import AuthenticateUseCase
from auth.application.use_cases.grant_user_role_use_case import GrantUserRoleUseCase
from auth.application.use_cases.refresh_token_use_case import RefreshTokenUseCase
from auth.domain.ports.cipher_port import CipherPort
from auth.domain.ports.credential_repository import CredentialRepository
from auth.domain.ports.oauth_client_port import OAuthClientPort
from auth.domain.ports.oauth_connection_repository import OAuthConnectionRepository
from auth.domain.ports.session_repository import SessionRepository
from auth.domain.ports.user_repository import UserRepository
from auth.domain.services.permission_resolver import PermissionResolver
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from storage.repositories.pg_credential_repository import PgCredentialRepository
from storage.repositories.pg_oauth_repository import PgOAuthRepository
from storage.repositories.pg_session_repository import PgSessionRepository
from storage.repositories.pg_user_repository import PgUserRepository

from app.config import Settings
from app.dependencies.database import get_db
from app.dependencies.settings import get_settings


@lru_cache(maxsize=1)
def get_jwt_adapter() -> JWTAdapter:
    return JWTAdapter()


@lru_cache(maxsize=1)
def get_cipher() -> CipherPort:
    return AESGCMCipher()


def get_google_oauth(settings: Settings = Depends(get_settings)) -> OAuthClientPort:
    return GoogleOAuthClient(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
    )


@lru_cache(maxsize=1)
def get_permission_resolver() -> PermissionResolver:
    return PermissionResolver()


def get_session_repository(session: AsyncSession = Depends(get_db)) -> SessionRepository:
    return PgSessionRepository(session)


def get_oauth_repository(session: AsyncSession = Depends(get_db)) -> OAuthConnectionRepository:
    return PgOAuthRepository(session)


def get_user_repository(session: AsyncSession = Depends(get_db)) -> UserRepository:
    return PgUserRepository(session)


def get_credential_repository(session: AsyncSession = Depends(get_db)) -> CredentialRepository:
    return PgCredentialRepository(session)


def get_authenticate_use_case(
    session_repo: SessionRepository = Depends(get_session_repository),
    oauth_repo: OAuthConnectionRepository = Depends(get_oauth_repository),
    user_repo: UserRepository = Depends(get_user_repository),
    credential_repo: CredentialRepository = Depends(get_credential_repository),
    cipher: CipherPort = Depends(get_cipher),
    google_oauth: OAuthClientPort = Depends(get_google_oauth),
    jwt_adapter: JWTAdapter = Depends(get_jwt_adapter),
) -> AuthenticateUseCase:
    # user_repo: REQ-002 JIT auto-provisioning(PR #88) — 첫 SSO 로그인 시 users INSERT.
    # credential_repo: oauth_connections.credential_id FK 대상 credentials row 생성.
    return AuthenticateUseCase(
        session_repo=session_repo,
        oauth_repo=oauth_repo,
        user_repo=user_repo,
        credential_repo=credential_repo,
        cipher=cipher,
        google_oauth=google_oauth,
        jwt_adapter=jwt_adapter,
    )


def get_refresh_token_use_case(
    session_repo: SessionRepository = Depends(get_session_repository),
    jwt_adapter: JWTAdapter = Depends(get_jwt_adapter),
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(session_repo=session_repo, jwt_adapter=jwt_adapter)


def get_grant_user_role_use_case(
    user_repo: UserRepository = Depends(get_user_repository),
) -> GrantUserRoleUseCase:
    return GrantUserRoleUseCase(user_repo=user_repo)
