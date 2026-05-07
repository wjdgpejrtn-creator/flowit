import pytest
from uuid import uuid4

from auth.domain.services.credential_injection import CredentialInjectionService
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
async def test_inject_returns_plaintext(oauth_repo, cipher):
    node_def = _NodeDef()
    node_repo = _NodeRepo(node_def)
    user_id = uuid4()
    plaintext = b"my_access_token"
    conn = await oauth_repo.create(
        user_id=user_id,
        service="google",
        tokens={
            "access_token_encrypted": cipher.encrypt(plaintext),
            "refresh_token_encrypted": cipher.encrypt(b"refresh"),
            "scopes": ["email"],
        },
    )

    service = CredentialInjectionService(cipher, oauth_repo, node_repo)
    credential = await service.inject(conn.oauth_id, node_def.node_id)

    assert credential.value == plaintext.decode()
    assert credential.credential_id == str(conn.oauth_id)


@pytest.mark.asyncio
async def test_inject_inactive_raises(oauth_repo, cipher):
    node_def = _NodeDef()
    node_repo = _NodeRepo(node_def)
    user_id = uuid4()
    conn = await oauth_repo.create(
        user_id=user_id,
        service="google",
        tokens={
            "access_token_encrypted": cipher.encrypt(b"token"),
            "refresh_token_encrypted": cipher.encrypt(b"refresh"),
            "scopes": [],
        },
    )
    await oauth_repo.revoke(conn.oauth_id)

    service = CredentialInjectionService(cipher, oauth_repo, node_repo)
    with pytest.raises(NotFoundError):
        await service.inject(conn.oauth_id, node_def.node_id)


@pytest.mark.asyncio
async def test_inject_restricted_node_raises(oauth_repo, cipher):
    node_def = _NodeDef(risk_level=RiskLevel.RESTRICTED)
    node_repo = _NodeRepo(node_def)
    user_id = uuid4()
    conn = await oauth_repo.create(
        user_id=user_id,
        service="google",
        tokens={"access_token_encrypted": cipher.encrypt(b"t"), "scopes": []},
    )

    service = CredentialInjectionService(cipher, oauth_repo, node_repo)
    with pytest.raises(AuthorizationError):
        await service.inject(conn.oauth_id, node_def.node_id)


@pytest.mark.asyncio
async def test_inject_node_not_found_raises(oauth_repo, cipher):
    node_repo = _NodeRepo(node_def=None)
    service = CredentialInjectionService(cipher, oauth_repo, node_repo)
    with pytest.raises(NotFoundError):
        await service.inject(uuid4(), uuid4())
