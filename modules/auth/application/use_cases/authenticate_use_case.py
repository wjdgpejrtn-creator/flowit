from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta

from ...domain.ports.cipher_port import CipherPort
from ...domain.ports.oauth_client_port import OAuthClientPort
from ...domain.ports.oauth_connection_repository import OAuthConnectionRepository
from ...domain.ports.session_repository import SessionRepository
from ...domain.value_objects.token_pair import TokenPair


class AuthenticateUseCase:
    def __init__(
        self,
        session_repo: SessionRepository,
        oauth_repo: OAuthConnectionRepository,
        cipher: CipherPort,
        google_oauth: OAuthClientPort,
        jwt_adapter: object,
    ) -> None:
        self._session_repo = session_repo
        self._oauth_repo = oauth_repo
        self._cipher = cipher
        self._google_oauth = google_oauth
        self._jwt_adapter = jwt_adapter

    async def execute(self, code: str) -> TokenPair:
        user_info = await self._google_oauth.exchange_code(code)

        # Derive deterministic user_id from Google subject identifier
        google_sub: str = user_info["sub"]
        user_id = uuid.uuid5(uuid.NAMESPACE_DNS, google_sub)

        # Encrypt OAuth tokens before storing
        enc_access = self._cipher.encrypt(user_info["access_token"].encode())
        enc_refresh = self._cipher.encrypt(user_info.get("refresh_token", "").encode())
        scopes: list[str] = user_info.get("scopes", [])

        # Upsert OAuth connection (revoke old, create new)
        existing = await self._oauth_repo.get_active_for_user(user_id, "google")
        if existing is not None:
            await self._oauth_repo.update_tokens(
                existing.oauth_id,
                new_tokens={"access_token_encrypted": enc_access, "refresh_token_encrypted": enc_refresh},
            )
        else:
            await self._oauth_repo.create(
                user_id=user_id,
                service="google",
                tokens={
                    "access_token_encrypted": enc_access,
                    "refresh_token_encrypted": enc_refresh,
                    "scopes": scopes,
                },
            )

        # Create session
        session_hash = hashlib.sha256(os.urandom(32)).hexdigest()
        expiry = int(os.getenv("JWT_EXPIRY_SECONDS", "3600"))
        expires_at = datetime.now(UTC) + timedelta(seconds=expiry)
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
        }, ttl_seconds=expiry * 7)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expiry,
        )
