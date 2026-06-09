from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from auth.domain.entities.credential import Credential
from auth.domain.entities.oauth_connection import OAuthConnection
from auth.domain.entities.session import Session
from auth.domain.entities.user import User, UserRole
from auth.domain.ports.cipher_port import CipherPort
from auth.domain.ports.credential_repository import CredentialRepository
from auth.domain.ports.oauth_connection_repository import OAuthConnectionRepository
from auth.domain.ports.session_repository import SessionRepository
from auth.domain.ports.user_repository import UserRepository


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

    async def find_by_hash(self, session_hash: str) -> Session | None:
        return self._store.get(session_hash)

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
        # credentials row를 backing으로 갖는 경우 tokens로 credential_id 전달 —
        # 없으면 oauth_id를 그대로 사용 (기존 호출자 호환).
        credential_id = tokens.get("credential_id", oid)
        conn = OAuthConnection(
            oauth_id=oid,
            user_id=user_id,
            service=service,
            credential_id=credential_id,
            access_token_encrypted=tokens["access_token_encrypted"],
            refresh_token_encrypted=tokens.get("refresh_token_encrypted"),
            scopes=tokens.get("scopes", []),
            account_id=tokens.get("account_id"),
            display_name=tokens.get("display_name"),
            connected_at=datetime.now(UTC),
        )
        self._store[str(credential_id)] = conn
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

    async def list_for_user(self, user_id):
        return [c for c in self._store.values() if c.user_id == user_id and c.is_active]

    async def list_connection_audit(self, limit: int = 200, offset: int = 0):
        # in-memory fake — 소유자 정보 join 없이 connection 필드만 채운다(감사 단위 테스트는
        # use case의 Admin 게이트를 주로 검증하므로 owner 메타는 placeholder).
        from auth.domain.value_objects.connection_audit_entry import ConnectionAuditEntry

        rows = sorted(self._store.values(), key=lambda c: c.connected_at, reverse=True)
        return [
            ConnectionAuditEntry(
                oauth_id=c.oauth_id,
                user_id=c.user_id,
                owner_email="",
                owner_name="",
                owner_department=None,
                service=c.service,
                account_id=c.account_id,
                display_name=c.display_name,
                scopes=list(c.scopes),
                is_active=c.is_active,
                connected_at=c.connected_at,
                last_refreshed_at=c.last_refreshed_at,
            )
            for c in rows[offset : offset + limit]
        ]


class FakeCipher(CipherPort):
    def encrypt(self, plaintext: bytes) -> bytes:
        return b"ENC:" + plaintext

    def decrypt(self, ciphertext: bytes) -> bytes:
        return ciphertext.removeprefix(b"ENC:")


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._store: dict = {}

    async def find_by_id(self, user_id) -> User | None:
        return self._store.get(user_id)

    async def find_by_email(self, email: str) -> User | None:
        for user in self._store.values():
            if user.email == email:
                return user
        return None

    async def create(
        self,
        user_id,
        email: str,
        name: str,
        role: UserRole = "User",
        department_id=None,
    ) -> User:
        now = datetime.now(UTC)
        user = User(
            user_id=user_id,
            email=email,
            name=name,
            role=role,
            department_id=department_id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self._store[user_id] = user
        return user

    async def update_role(self, user_id, role: UserRole) -> None:
        if user_id in self._store:
            self._store[user_id] = self._store[user_id].model_copy(
                update={"role": role, "updated_at": datetime.now(UTC)}
            )

    async def update_department(self, user_id, department_id) -> None:
        if user_id in self._store:
            self._store[user_id] = self._store[user_id].model_copy(
                update={"department_id": department_id, "updated_at": datetime.now(UTC)}
            )


class InMemoryCredentialRepository(CredentialRepository):
    def __init__(self) -> None:
        self._store: dict = {}

    async def create(self, user_id, name, credential_kind, encrypted_data, metadata=None) -> Credential:
        now = datetime.now(UTC)
        cred = Credential(
            credential_id=uuid4(),
            user_id=user_id,
            name=name,
            credential_kind=credential_kind,
            encrypted_data=encrypted_data,
            metadata=metadata or {},
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self._store[cred.credential_id] = cred
        return cred

    async def get_by_id(self, credential_id) -> Credential | None:
        return self._store.get(credential_id)

    async def update_data(self, credential_id, encrypted_data: bytes) -> None:
        if credential_id in self._store:
            self._store[credential_id] = self._store[credential_id].model_copy(
                update={"encrypted_data": encrypted_data, "updated_at": datetime.now(UTC)}
            )


@pytest.fixture
def session_repo() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def credential_repo() -> InMemoryCredentialRepository:
    return InMemoryCredentialRepository()


@pytest.fixture
def oauth_repo() -> InMemoryOAuthRepository:
    return InMemoryOAuthRepository()


@pytest.fixture
def cipher() -> FakeCipher:
    return FakeCipher()


@pytest.fixture
def user_repo() -> InMemoryUserRepository:
    return InMemoryUserRepository()


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
