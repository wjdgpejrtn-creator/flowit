import pytest
from uuid import uuid4

from auth.application.use_cases.inject_credential import InjectCredentialUseCase
from auth.domain.services.credential_injection import CredentialInjectionService
from common_schemas.exceptions import NotFoundError


@pytest.mark.asyncio
async def test_inject_credential_returns_plaintext(oauth_repo, cipher):
    user_id = uuid4()
    plaintext = b"secret_access_token"
    conn = await oauth_repo.create(
        user_id=user_id,
        service="google",
        encrypted_access_token=cipher.encrypt(plaintext),
        encrypted_refresh_token=cipher.encrypt(b"refresh"),
        scopes=["email"],
    )

    service = CredentialInjectionService(oauth_repo, cipher)
    uc = InjectCredentialUseCase(service)
    credential = await uc.execute(conn.oauth_id)

    assert credential.value == plaintext.decode()
    assert credential.credential_id == str(conn.oauth_id)


@pytest.mark.asyncio
async def test_inject_credential_revoked_raises(oauth_repo, cipher):
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
    uc = InjectCredentialUseCase(service)
    with pytest.raises(NotFoundError):
        await uc.execute(conn.oauth_id)


@pytest.mark.asyncio
async def test_inject_credential_not_found_raises(oauth_repo, cipher):
    service = CredentialInjectionService(oauth_repo, cipher)
    uc = InjectCredentialUseCase(service)
    with pytest.raises(NotFoundError):
        await uc.execute(uuid4())
