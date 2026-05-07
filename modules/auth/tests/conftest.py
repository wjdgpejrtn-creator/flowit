from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from auth.domain.entities.oauth_connection import OAuthConnection
from auth.domain.entities.session import Session
from auth.domain.ports.cipher_port import CipherPort
from auth.domain.ports.oauth_repository import OAuthConnectionRepository
from auth.domain.ports.session_repository import SessionRepository


class InMemorySessionRepository(SessionRepository):
    def __init__(self) -> None:
        self._store: dict = {}

    async def create(self, user_id, session_hash, expires_at) -> Session:
        session = Session(
            session_id=uuid4(),
            user_id=user_id,
            session_hash=session_hash,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        )
        self._store[session_hash] = session
        return session

    async def find_by_hash(self, session_hash: str) -> Session:
        session = self._store.get(session_hash)
        if session is None:
            from common_schemas.exceptions import NotFoundError
            raise NotFoundError(f"Session not found: {session_hash}")
        return session

    async def revoke(self, session_id) -> None:
        for key, s in list(self._store.items()):
            if s.session_id == session_id:
                self._store[key] = s.model_copy(update={"is_revoked": True})

    async def revoke_all_for_user(self, user_id) -> int:
        count = 0
        for key in list(self._store):
            s = self._store[key]
            if s.user_id == user_id:
                self._store[key] = s.model_copy(update={"is_revoked": True})
                count += 1
        return count


class InMemoryOAuthRepository(OAuthConnectionRepository):
    def __init__(self) -> None:
        self._store: dict = {}

    async def create(self, user_id, service, encrypted_access_token, encrypted_refresh_token, scopes, token_expires_at=None) -> OAuthConnection:
        conn = OAuthConnection(
            oauth_id=uuid4(),
            user_id=user_id,
            service=service,
            encrypted_access_token=encrypted_access_token,
            encrypted_refresh_token=encrypted_refresh_token,
            scopes=scopes,
            token_expires_at=token_expires_at,
            created_at=datetime.now(timezone.utc),
        )
        self._store[str(conn.oauth_id)] = conn
        return conn

    async def get_by_credential_id(self, credential_id) -> OAuthConnection:
        conn = self._store.get(str(credential_id))
        if conn is None:
            from common_schemas.exceptions import NotFoundError
            raise NotFoundError(str(credential_id))
        return conn

    async def get_active_for_user(self, user_id, service) -> OAuthConnection:
        for conn in self._store.values():
            if conn.user_id == user_id and conn.service == service and not conn.is_revoked:
                return conn
        from common_schemas.exceptions import NotFoundError
        raise NotFoundError(f"No active {service} connection for {user_id}")

    async def update_tokens(self, credential_id, encrypted_access_token, encrypted_refresh_token) -> None:
        key = str(credential_id)
        if key in self._store:
            c = self._store[key]
            self._store[key] = c.model_copy(update={
                "encrypted_access_token": encrypted_access_token,
                "encrypted_refresh_token": encrypted_refresh_token,
            })

    async def revoke(self, credential_id) -> None:
        key = str(credential_id)
        if key in self._store:
            self._store[key] = self._store[key].model_copy(update={"is_revoked": True})


class FakeCipher(CipherPort):
    def encrypt(self, plaintext: bytes) -> bytes:
        return b"ENC:" + plaintext

    def decrypt(self, ciphertext: bytes) -> bytes:
        return ciphertext.removeprefix(b"ENC:")


@pytest.fixture
def session_repo() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def oauth_repo() -> InMemoryOAuthRepository:
    return InMemoryOAuthRepository()


@pytest.fixture
def cipher() -> FakeCipher:
    return FakeCipher()


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def valid_session(user_id):
    return Session(
        session_id=uuid4(),
        user_id=user_id,
        session_hash="test_hash_abc",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_at=datetime.now(timezone.utc),
    )
