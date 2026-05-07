from __future__ import annotations

from datetime import UTC, datetime
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

    async def create(self, user_id, session_hash, **kwargs) -> Session:
        session = Session(
            session_id=uuid4(),
            user_id=user_id,
            session_hash=session_hash,
            expires_at=kwargs["expires_at"],
            created_at=datetime.now(UTC),
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
                s.revoke()

    async def revoke_all_for_user(self, user_id) -> int:
        count = 0
        for s in self._store.values():
            if s.user_id == user_id:
                s.revoke()
                count += 1
        return count


class InMemoryOAuthRepository(OAuthConnectionRepository):
    def __init__(self) -> None:
        self._store: dict = {}

    async def create(self, user_id, service, tokens: dict) -> OAuthConnection:
        oid = uuid4()
        conn = OAuthConnection(
            oauth_id=oid,
            user_id=user_id,
            service=service,
            credential_id=oid,
            access_token_encrypted=tokens["access_token_encrypted"],
            refresh_token_encrypted=tokens.get("refresh_token_encrypted"),
            scopes=tokens.get("scopes", []),
            connected_at=datetime.now(UTC),
        )
        self._store[str(conn.oauth_id)] = conn
        return conn

    async def get_by_credential_id(self, credential_id):
        return self._store.get(str(credential_id))

    async def get_active_for_user(self, user_id, service):
        for conn in self._store.values():
            if conn.user_id == user_id and conn.service == service and conn.is_active:
                return conn
        return None

    async def update_tokens(self, credential_id, new_tokens: dict) -> None:
        key = str(credential_id)
        if key in self._store:
            c = self._store[key]
            if "access_token_encrypted" in new_tokens:
                c.access_token_encrypted = new_tokens["access_token_encrypted"]
            if "refresh_token_encrypted" in new_tokens:
                c.refresh_token_encrypted = new_tokens["refresh_token_encrypted"]

    async def revoke(self, credential_id) -> None:
        key = str(credential_id)
        if key in self._store:
            self._store[key].revoke()


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
    from datetime import timedelta
    return Session(
        session_id=uuid4(),
        user_id=user_id,
        session_hash="test_hash_abc",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        created_at=datetime.now(UTC),
    )
