from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta

from ...domain.ports.cipher_port import CipherPort
from ...domain.ports.credential_repository import CredentialRepository
from ...domain.ports.oauth_client_port import OAuthClientPort
from ...domain.ports.oauth_connection_repository import OAuthConnectionRepository
from ...domain.ports.session_repository import SessionRepository
from ...domain.ports.user_repository import UserRepository
from ...domain.value_objects.token_pair import TokenPair


class AuthenticateUseCase:
    def __init__(
        self,
        session_repo: SessionRepository,
        oauth_repo: OAuthConnectionRepository,
        user_repo: UserRepository,
        credential_repo: CredentialRepository,
        cipher: CipherPort,
        google_oauth: OAuthClientPort,
        jwt_adapter: object,
    ) -> None:
        self._session_repo = session_repo
        self._oauth_repo = oauth_repo
        self._user_repo = user_repo
        self._credential_repo = credential_repo
        self._cipher = cipher
        self._google_oauth = google_oauth
        self._jwt_adapter = jwt_adapter

    async def execute(self, code: str) -> TokenPair:
        user_info = await self._google_oauth.exchange_code(code)

        # Derive deterministic user_id from Google subject identifier
        google_sub: str = user_info["sub"]
        user_id = uuid.uuid5(uuid.NAMESPACE_DNS, google_sub)

        # JIT auto-provisioning — INSERT users row on first SSO login
        if await self._user_repo.find_by_id(user_id) is None:
            email: str = user_info["email"]
            await self._user_repo.create(
                user_id=user_id,
                email=email,
                name=user_info.get("name") or email.split("@")[0],
                role="User",
                department_id=None,
            )

        # Encrypt OAuth tokens before storing
        enc_access = self._cipher.encrypt(user_info["access_token"].encode())
        enc_refresh = self._cipher.encrypt(user_info.get("refresh_token", "").encode())
        scopes: list[str] = user_info.get("scopes", [])

        # Upsert OAuth connection. oauth_connections.credential_id는 credentials FK(NOT NULL)이므로
        # credentials row를 먼저 생성/갱신한 뒤 그 credential_id로 oauth_connection을 연결한다.
        existing = await self._oauth_repo.get_active_for_user(user_id, "google")
        if existing is not None:
            await self._credential_repo.update_data(existing.credential_id, enc_access)
            await self._oauth_repo.update_tokens(
                existing.credential_id,
                new_tokens={"access_token_encrypted": enc_access, "refresh_token_encrypted": enc_refresh},
            )
        else:
            credential = await self._credential_repo.create(
                user_id=user_id,
                name="Google OAuth",
                credential_kind="oauth_token",
                encrypted_data=enc_access,
                metadata={"service": "google", "scopes": scopes},
            )
            await self._oauth_repo.create(
                user_id=user_id,
                service="google",
                tokens={
                    "credential_id": credential.credential_id,
                    "access_token_encrypted": enc_access,
                    "refresh_token_encrypted": enc_refresh,
                    "scopes": scopes,
                },
            )

        # Create session. session expires_at은 refresh_token TTL과 동일하게 둔다.
        # access TTL(1h)에 맞추면 access 만료 후 refresh 시 RefreshTokenUseCase가
        # 이미 만료된 session을 만나 E-AUTH-006으로 거부 → refresh가 사실상 작동 불가.
        session_hash = hashlib.sha256(os.urandom(32)).hexdigest()
        expiry = int(os.getenv("JWT_EXPIRY_SECONDS", "3600"))
        refresh_expiry = expiry * 7
        expires_at = datetime.now(UTC) + timedelta(seconds=refresh_expiry)
        await self._session_repo.create(user_id, session_hash, expires_at=expires_at)

        # Issue JWT pair
        access_token: str = self._jwt_adapter.encode({
            "sub": str(user_id),
            "session_hash": session_hash,
            "type": "access",
        })
        refresh_token: str = self._jwt_adapter.encode({
            "sub": str(user_id),
            "session_hash": session_hash,
            "type": "refresh",
        }, ttl_seconds=refresh_expiry)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expiry,
        )
