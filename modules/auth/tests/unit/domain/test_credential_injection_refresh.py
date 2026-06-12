"""CredentialInjectionService access token refresh (REQ-002 #452 ②).

게시 스킬 워크플로우 실행 시 google access token이 1시간 후 만료되어 401이 나는 문제.
`_resolve_oauth`가 만료 임박/만료 시 refresh_token으로 access token을 갱신하고 영속화한다.

- oauth_clients: dict[str, OAuthClientPort] (service-agnostic, 조장 승인). 현재 google만.
- 미배선/레거시(expires_at NULL): best-effort — 갱신 가능하면 하고, 불가하면 현재 토큰 사용.
- known-expired인데 갱신 불가/실패: AuthorizationError(E-CRED-002) — 침묵 401보다 명확한 에러.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from auth.domain.services.credential_injection_service import CredentialInjectionService
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import AuthorizationError


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


class FakeOAuthClient:
    """refresh_access_token만 사용 — 호출 기록 + 응답/예외 주입."""

    def __init__(self, new_access="new_token", expires_in=3600, raises=False):
        self._new_access = new_access
        self._expires_in = expires_in
        self._raises = raises
        self.refresh_calls: list[str] = []

    def authorization_url(self, state, scopes=None, redirect_uri=None) -> str:
        return ""

    async def exchange_code(self, code, redirect_uri=None) -> dict:
        return {}

    async def refresh_access_token(self, refresh_token: str) -> dict:
        self.refresh_calls.append(refresh_token)
        if self._raises:
            raise RuntimeError("google token endpoint 500")
        return {"access_token": self._new_access, "expires_in": self._expires_in}

    async def get_user_info(self, access_token) -> dict:
        return {}


async def _make_oauth_credential(
    oauth_repo, cipher, credential_repo, *, expires_at, access=b"old_token", refresh=b"refresh"
):
    user_id = uuid4()
    cred = await credential_repo.create(
        user_id=user_id, name="google-oauth", credential_kind="oauth_token",
        encrypted_data=b"oauth-backing", metadata={},
    )
    await oauth_repo.create(
        user_id=user_id, service="google",
        tokens={
            "credential_id": cred.credential_id,
            "access_token_encrypted": cipher.encrypt(access),
            "refresh_token_encrypted": cipher.encrypt(refresh) if refresh else None,
            "scopes": ["email"],
            "access_token_expires_at": expires_at,
        },
    )
    return cred


@pytest.mark.asyncio
async def test_valid_token_no_refresh(oauth_repo, cipher, credential_repo):
    """만료 여유 있으면 refresh 호출 안 하고 현재 토큰 그대로 주입."""
    node_def = _NodeDef()
    client = FakeOAuthClient()
    service = CredentialInjectionService(
        cipher, oauth_repo, _NodeRepo(node_def), credential_repo,
        oauth_clients={"google": client},
    )
    cred = await _make_oauth_credential(
        oauth_repo, cipher, credential_repo,
        expires_at=datetime.now(UTC) + timedelta(hours=1), access=b"old_token",
    )

    result = await service.inject(cred.credential_id, node_def.node_id)

    assert result.value == "old_token"
    assert client.refresh_calls == []  # 갱신 미발생


@pytest.mark.asyncio
async def test_expired_token_refreshes_and_persists(oauth_repo, cipher, credential_repo):
    """만료된 토큰 → refresh 호출 → 새 토큰 주입 + oauth_connections 영속화."""
    node_def = _NodeDef()
    client = FakeOAuthClient(new_access="fresh_token", expires_in=3600)
    service = CredentialInjectionService(
        cipher, oauth_repo, _NodeRepo(node_def), credential_repo,
        oauth_clients={"google": client},
    )
    cred = await _make_oauth_credential(
        oauth_repo, cipher, credential_repo,
        expires_at=datetime.now(UTC) - timedelta(minutes=1), access=b"old_token", refresh=b"my_refresh",
    )

    result = await service.inject(cred.credential_id, node_def.node_id)

    assert result.value == "fresh_token"  # 새 토큰 주입
    assert client.refresh_calls == ["my_refresh"]  # refresh_token 평문으로 호출
    # 영속화 검증 — 저장된 access_token이 새 토큰으로 갱신 + expires_at 미래로 갱신
    conn = await oauth_repo.get_by_credential_id(cred.credential_id)
    assert cipher.decrypt(conn.access_token_encrypted) == b"fresh_token"
    assert conn.access_token_expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_near_expiry_within_skew_refreshes(oauth_repo, cipher, credential_repo):
    """아직 만료 전이지만 skew(60s) 이내면 선제 갱신 — 실행 도중 만료 방지."""
    node_def = _NodeDef()
    client = FakeOAuthClient(new_access="fresh_token")
    service = CredentialInjectionService(
        cipher, oauth_repo, _NodeRepo(node_def), credential_repo,
        oauth_clients={"google": client},
    )
    cred = await _make_oauth_credential(
        oauth_repo, cipher, credential_repo,
        expires_at=datetime.now(UTC) + timedelta(seconds=30),
    )

    result = await service.inject(cred.credential_id, node_def.node_id)

    assert result.value == "fresh_token"
    assert len(client.refresh_calls) == 1


@pytest.mark.asyncio
async def test_legacy_null_expiry_best_effort_refresh(oauth_repo, cipher, credential_repo):
    """레거시 connection(expires_at NULL) — best-effort로 갱신 시도 후 backfill."""
    node_def = _NodeDef()
    client = FakeOAuthClient(new_access="fresh_token")
    service = CredentialInjectionService(
        cipher, oauth_repo, _NodeRepo(node_def), credential_repo,
        oauth_clients={"google": client},
    )
    cred = await _make_oauth_credential(
        oauth_repo, cipher, credential_repo, expires_at=None,
    )

    result = await service.inject(cred.credential_id, node_def.node_id)

    assert result.value == "fresh_token"
    conn = await oauth_repo.get_by_credential_id(cred.credential_id)
    assert conn.access_token_expires_at is not None  # backfill 완료


@pytest.mark.asyncio
async def test_legacy_null_refresh_failure_falls_back_to_current(oauth_repo, cipher, credential_repo):
    """레거시 NULL + refresh 실패 → 현재 토큰으로 best-effort fallback (hard-fail 안 함)."""
    node_def = _NodeDef()
    client = FakeOAuthClient(raises=True)
    service = CredentialInjectionService(
        cipher, oauth_repo, _NodeRepo(node_def), credential_repo,
        oauth_clients={"google": client},
    )
    cred = await _make_oauth_credential(
        oauth_repo, cipher, credential_repo, expires_at=None, access=b"old_token",
    )

    result = await service.inject(cred.credential_id, node_def.node_id)
    assert result.value == "old_token"


@pytest.mark.asyncio
async def test_expired_no_client_raises(oauth_repo, cipher, credential_repo):
    """known-expired인데 service client 미배선 → AuthorizationError (침묵 401 차단)."""
    node_def = _NodeDef()
    service = CredentialInjectionService(
        cipher, oauth_repo, _NodeRepo(node_def), credential_repo,
        oauth_clients={},  # google client 미배선
    )
    cred = await _make_oauth_credential(
        oauth_repo, cipher, credential_repo,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    with pytest.raises(AuthorizationError):
        await service.inject(cred.credential_id, node_def.node_id)


@pytest.mark.asyncio
async def test_expired_refresh_failure_raises(oauth_repo, cipher, credential_repo):
    """known-expired + refresh 실패 → AuthorizationError(E-CRED-002)."""
    node_def = _NodeDef()
    client = FakeOAuthClient(raises=True)
    service = CredentialInjectionService(
        cipher, oauth_repo, _NodeRepo(node_def), credential_repo,
        oauth_clients={"google": client},
    )
    cred = await _make_oauth_credential(
        oauth_repo, cipher, credential_repo,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    with pytest.raises(AuthorizationError):
        await service.inject(cred.credential_id, node_def.node_id)


@pytest.mark.asyncio
async def test_no_oauth_clients_backward_compatible(oauth_repo, cipher, credential_repo):
    """oauth_clients 미지정(기존 호출자) + 유효 토큰 → 기존 동작 유지(refresh 없음)."""
    node_def = _NodeDef()
    service = CredentialInjectionService(cipher, oauth_repo, _NodeRepo(node_def), credential_repo)
    cred = await _make_oauth_credential(
        oauth_repo, cipher, credential_repo,
        expires_at=datetime.now(UTC) + timedelta(hours=1), access=b"valid_token",
    )

    result = await service.inject(cred.credential_id, node_def.node_id)
    assert result.value == "valid_token"
