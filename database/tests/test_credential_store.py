"""Encryption round-trip tests for CredentialStore (H-2 cipher DI)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.models.user import UserModel
from src.protocols import BaseCipher
from src.repositories.credential_store import CredentialStore


class NullCipher:
    """Passthrough cipher for testing (no actual encryption)."""

    def encrypt(self, plaintext: bytes) -> bytes:
        return b"ENC:" + plaintext

    def decrypt(self, ciphertext: bytes) -> bytes:
        assert ciphertext.startswith(b"ENC:")
        return ciphertext[4:]


@pytest.mark.asyncio
async def test_store_and_retrieve(db_session):
    cipher = NullCipher()
    assert isinstance(cipher, BaseCipher)

    user = UserModel(email="cred@test.com", name="Cred User")
    db_session.add(user)
    await db_session.flush()

    store = CredentialStore(db_session, cipher)
    cred_id = await store.store(
        user_id=user.id,
        name="My API Key",
        credential_kind="api_key",
        plaintext=b"secret-api-key-12345",
    )

    retrieved = await store.retrieve(cred_id)
    assert retrieved == b"secret-api-key-12345"


@pytest.mark.asyncio
async def test_delete_credential(db_session):
    cipher = NullCipher()
    user = UserModel(email="cred_del@test.com", name="Del User")
    db_session.add(user)
    await db_session.flush()

    store = CredentialStore(db_session, cipher)
    cred_id = await store.store(
        user_id=user.id,
        name="Temp Key",
        credential_kind="password",
        plaintext=b"temp-pass",
    )

    deleted = await store.delete_credential(cred_id)
    assert deleted is True

    from src.repositories.base import EntityNotFoundError

    with pytest.raises(EntityNotFoundError):
        await store.retrieve(cred_id)
