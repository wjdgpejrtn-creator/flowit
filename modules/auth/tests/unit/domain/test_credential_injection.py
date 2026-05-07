import pytest
from datetime import datetime, timezone
from uuid import uuid4

from auth.domain.entities.oauth_connection import OAuthConnection
from auth.domain.services.credential_injection import CredentialInjectionService
from common_schemas.exceptions import NotFoundError


@pytest.mark.asyncio
async def test_inject_returns_plaintext(oauth_repo, cipher):
    user_id = uuid4()
    plaintext = b"my_access_token"
    conn = await oauth_repo.create(
        user_id=user_id,
        service="google",
        encrypted_access_token=cipher.encrypt(plaintext),
        encrypted_refresh_token=cipher.encrypt(b"refresh"),
        scopes=["email"],
    )

    service = CredentialInjectionService(oauth_repo, cipher)
    credential = await service.inject(conn.oauth_id)

    assert credential.value == plaintext.decode()
    assert credential.credential_id == str(conn.oauth_id)


@pytest.mark.asyncio
async def test_inject_revoked_raises(oauth_repo, cipher):
    user_id = uuid4()
    conn = await oauth_repo.create(
        user_id=user_id,
        service="google",
        encrypted_access_token=cipher.encrypt(b"token"),
        encrypted_refresh_token=cipher.encrypt(b"refresh"),
        scopes=[],
    )
    await oauth_repo.revoke(conn.oauth_id)

    service = CredentialInjectionService(oauth_repo, cipher)
    with pytest.raises(NotFoundError):
        await service.inject(conn.oauth_id)
