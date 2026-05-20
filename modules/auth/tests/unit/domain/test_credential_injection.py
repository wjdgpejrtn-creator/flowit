from uuid import uuid4

import pytest
from auth.domain.services.credential_injection_service import CredentialInjectionService
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import AuthorizationError, NotFoundError


class _NodeRepo:
    def __init__(self, node_def=None):
        self._def = node_def

    async def get_by_id(self, node_id):
        return self._def

    async def upsert(self, d): return d
    async def list_all(self, mvp_only=False): return []
    async def search_by_embedding(self, q, limit=10): return []


class _NodeDef:
    def __init__(self, risk_level=RiskLevel.LOW, required_connections=None, service_type=None):
        self.node_id = uuid4()
        self.risk_level = risk_level
        self.required_connections = required_connections or []
        self.service_type = service_type


@pytest.mark.asyncio
async def test_inject_oauth_returns_plaintext(oauth_repo, cipher, credential_repo):
    """oauth_token credential — oauth_connections로 enrich 후 access_token 복호화."""
    node_def = _NodeDef()
    service = CredentialInjectionService(cipher, oauth_repo, _NodeRepo(node_def), credential_repo)
    user_id = uuid4()
    plaintext = b"my_access_token"

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

    credential = await service.inject(cred.credential_id, node_def.node_id)
    assert credential.value == plaintext.decode()
    assert credential.credential_id == str(cred.credential_id)


@pytest.mark.asyncio
async def test_inject_api_key_returns_plaintext(oauth_repo, cipher, credential_repo):
    """api_key credential — oauth_connections 없이 encrypted_data 직접 복호화 (ADR-0018 Decision 6).

    node_def에 required_connections가 있어도 api_key 경로는 service-match를 적용하지 않는다.
    """
    node_def = _NodeDef(required_connections=["anthropic"], service_type="anthropic")
    service = CredentialInjectionService(cipher, oauth_repo, _NodeRepo(node_def), credential_repo)
    secret = b"sk-ant-xxxxx"

    cred = await credential_repo.create(
        user_id=uuid4(), name="anthropic-key", credential_kind="api_key",
        encrypted_data=cipher.encrypt(secret), metadata={},
    )

    credential = await service.inject(cred.credential_id, node_def.node_id)
    assert credential.value == secret.decode()


@pytest.mark.asyncio
async def test_inject_oauth_inactive_conn_raises(oauth_repo, cipher, credential_repo):
    node_def = _NodeDef()
    service = CredentialInjectionService(cipher, oauth_repo, _NodeRepo(node_def), credential_repo)
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
        await service.inject(cred.credential_id, node_def.node_id)


@pytest.mark.asyncio
async def test_inject_credential_not_found_raises(oauth_repo, cipher, credential_repo):
    """credentials 테이블에 credential_id row 없음 → NotFoundError."""
    node_def = _NodeDef()
    service = CredentialInjectionService(cipher, oauth_repo, _NodeRepo(node_def), credential_repo)
    with pytest.raises(NotFoundError):
        await service.inject(uuid4(), node_def.node_id)


@pytest.mark.asyncio
async def test_inject_restricted_node_raises(oauth_repo, cipher, credential_repo):
    node_def = _NodeDef(risk_level=RiskLevel.RESTRICTED)
    service = CredentialInjectionService(cipher, oauth_repo, _NodeRepo(node_def), credential_repo)
    with pytest.raises(AuthorizationError):
        await service.inject(uuid4(), node_def.node_id)


@pytest.mark.asyncio
async def test_inject_node_not_found_raises(oauth_repo, cipher, credential_repo):
    service = CredentialInjectionService(cipher, oauth_repo, _NodeRepo(node_def=None), credential_repo)
    with pytest.raises(NotFoundError):
        await service.inject(uuid4(), uuid4())
