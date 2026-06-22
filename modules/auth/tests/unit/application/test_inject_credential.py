from uuid import uuid4

import pytest
from auth.application.use_cases.inject_credential_use_case import InjectCredentialUseCase
from auth.domain.services.credential_injection_service import CredentialInjectionService
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import NotFoundError


class _NodeRepo:
    def __init__(self, node_def=None):
        self._def = node_def

    async def get_by_id(self, node_id):
        return self._def

    async def upsert(self, d): return d
    async def list_all(self, mvp_only=False): return []
    async def search_by_embedding(self, q, limit=10): return []


class _NodeDef:
    def __init__(self):
        self.node_id = uuid4()
        self.risk_level = RiskLevel.LOW
        self.required_connections = []
        self.service_type = None


@pytest.mark.asyncio
async def test_inject_credential_returns_plaintext(oauth_repo, cipher, credential_repo):
    node_def = _NodeDef()
    service = CredentialInjectionService(cipher, oauth_repo, _NodeRepo(node_def), credential_repo)
    uc = InjectCredentialUseCase(service)
    user_id = uuid4()
    plaintext = b"secret_access_token"

    cred = await credential_repo.create(
        user_id=user_id, name="google-oauth", credential_kind="oauth_token",
        encrypted_data=b"oauth-backing", metadata={},
    )
    await oauth_repo.create(
        user_id=user_id, service="google",
        tokens={
            "credential_id": cred.credential_id,
            "access_token_encrypted": cipher.encrypt(plaintext),
            "refresh_token_encrypted": cipher.encrypt(b"refresh"),
            "scopes": ["email"],
        },
    )

    credential = await uc.execute(cred.credential_id, node_def.node_id)
    assert credential.value == plaintext.decode()
    assert credential.credential_id == str(cred.credential_id)


@pytest.mark.asyncio
async def test_inject_credential_revoked_raises(oauth_repo, cipher, credential_repo):
    node_def = _NodeDef()
    service = CredentialInjectionService(cipher, oauth_repo, _NodeRepo(node_def), credential_repo)
    uc = InjectCredentialUseCase(service)
    user_id = uuid4()

    cred = await credential_repo.create(
        user_id=user_id, name="google-oauth", credential_kind="oauth_token",
        encrypted_data=b"oauth-backing", metadata={},
    )
    await oauth_repo.create(
        user_id=user_id, service="google",
        tokens={
            "credential_id": cred.credential_id,
            "access_token_encrypted": cipher.encrypt(b"token"),
            "scopes": [],
        },
    )
    await oauth_repo.revoke(cred.credential_id)

    with pytest.raises(NotFoundError):
        await uc.execute(cred.credential_id, node_def.node_id)


@pytest.mark.asyncio
async def test_inject_credential_not_found_raises(oauth_repo, cipher, credential_repo):
    service = CredentialInjectionService(cipher, oauth_repo, _NodeRepo(node_def=None), credential_repo)
    uc = InjectCredentialUseCase(service)
    with pytest.raises(NotFoundError):
        await uc.execute(uuid4(), uuid4())
