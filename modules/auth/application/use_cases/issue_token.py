from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from common_schemas.exceptions import AuthorizationError

from ...domain.ports.session_repository import SessionRepository
from ...domain.value_objects.token_pair import TokenPair


class IssueTokenUseCase:
    def __init__(self, session_repo: SessionRepository, jwt_adapter: object) -> None:
        self._session_repo = session_repo
        self._jwt_adapter = jwt_adapter

    async def execute(self, session_hash: str) -> TokenPair:
        session = await self._session_repo.find_by_hash(session_hash)

        if not session.is_valid():
            raise AuthorizationError("Session is expired or revoked", code="E-AUTH-003")

        expiry = int(os.getenv("JWT_EXPIRY_SECONDS", "3600"))

        access_token: str = self._jwt_adapter.encode({
            "sub": str(session.user_id),
            "session_hash": session_hash,
            "type": "access",
        })
        refresh_token: str = self._jwt_adapter.encode({
            "sub": str(session.user_id),
            "session_hash": session_hash,
            "type": "refresh",
        }, ttl_seconds=expiry * 7)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expiry,
        )
