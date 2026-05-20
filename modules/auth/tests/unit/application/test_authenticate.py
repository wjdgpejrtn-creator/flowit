import uuid

import pytest
from auth.application.use_cases.authenticate_use_case import AuthenticateUseCase


class FakeGoogleOAuth:
    def __init__(self, sub: str = "google_sub_123", email: str = "user@example.com"):
        self._sub = sub
        self._email = email

    async def exchange_code(self, code: str) -> dict:
        return {
            "sub": self._sub,
            "email": self._email,
            "name": "Test User",
            "access_token": "goog_access_token",
            "refresh_token": "goog_refresh_token",
            "scopes": ["email", "profile"],
            "token_expires_at": None,
        }


class FakeJWT:
    def encode(self, payload: dict, ttl_seconds: int | None = None) -> str:
        parts = [f"{k}={v}" for k, v in payload.items()]
        return "tok:" + ",".join(parts)

    def decode(self, token: str) -> dict:
        raw = token.removeprefix("tok:")
        return dict(part.split("=", 1) for part in raw.split(","))


@pytest.mark.asyncio
async def test_authenticate_returns_token_pair(session_repo, oauth_repo, user_repo, credential_repo, cipher):
    uc = AuthenticateUseCase(session_repo, oauth_repo, user_repo, credential_repo, cipher, FakeGoogleOAuth(), FakeJWT())
    pair = await uc.execute("auth_code_abc")

    assert pair.access_token.startswith("tok:")
    assert pair.refresh_token.startswith("tok:")
    assert pair.token_type == "Bearer"


@pytest.mark.asyncio
async def test_authenticate_derives_deterministic_user_id(session_repo, oauth_repo, user_repo, credential_repo, cipher):
    google = FakeGoogleOAuth(sub="stable_sub_999")
    jwt = FakeJWT()
    uc = AuthenticateUseCase(session_repo, oauth_repo, user_repo, credential_repo, cipher, google, jwt)

    pair1 = await uc.execute("code_1")
    pair2 = await uc.execute("code_2")

    payload1 = jwt.decode(pair1.access_token)
    payload2 = jwt.decode(pair2.access_token)

    expected_user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "stable_sub_999"))
    assert payload1["sub"] == expected_user_id
    assert payload2["sub"] == expected_user_id


@pytest.mark.asyncio
async def test_authenticate_stores_encrypted_token(session_repo, oauth_repo, user_repo, credential_repo, cipher):
    google = FakeGoogleOAuth(sub="sub_encrypt_test")
    uc = AuthenticateUseCase(session_repo, oauth_repo, user_repo, credential_repo, cipher, google, FakeJWT())
    await uc.execute("code_xyz")

    user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "sub_encrypt_test")
    conn = await oauth_repo.get_active_for_user(user_id, "google")

    assert conn.access_token_encrypted != b"goog_access_token"
    assert cipher.decrypt(conn.access_token_encrypted) == b"goog_access_token"


@pytest.mark.asyncio
async def test_authenticate_second_login_updates_tokens(session_repo, oauth_repo, user_repo, credential_repo, cipher):
    google_first = FakeGoogleOAuth(sub="sub_reauth")
    uc = AuthenticateUseCase(session_repo, oauth_repo, user_repo, credential_repo, cipher, google_first, FakeJWT())
    await uc.execute("first_code")

    class FakeGoogleOAuthV2(FakeGoogleOAuth):
        async def exchange_code(self, code: str) -> dict:
            result = await super().exchange_code(code)
            result["access_token"] = "new_access_token"
            return result

    uc2 = AuthenticateUseCase(
        session_repo, oauth_repo, user_repo, credential_repo, cipher, FakeGoogleOAuthV2(sub="sub_reauth"), FakeJWT()
    )
    await uc2.execute("second_code")

    user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "sub_reauth")
    conn = await oauth_repo.get_active_for_user(user_id, "google")
    assert cipher.decrypt(conn.access_token_encrypted) == b"new_access_token"


# ── JIT user auto-provisioning (REQ-002 보강, 2026-05-19) ─────────────────


@pytest.mark.asyncio
async def test_jit_creates_new_user_on_first_login(session_repo, oauth_repo, user_repo, credential_repo, cipher):
    """첫 로그인 시 users 테이블에 INSERT (JIT auto-provisioning)."""
    google = FakeGoogleOAuth(sub="new_sub_jit", email="newuser@example.com")
    uc = AuthenticateUseCase(session_repo, oauth_repo, user_repo, credential_repo, cipher, google, FakeJWT())

    user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "new_sub_jit")
    assert await user_repo.find_by_id(user_id) is None

    await uc.execute("first_login_code")

    created = await user_repo.find_by_id(user_id)
    assert created is not None
    assert created.user_id == user_id
    assert created.email == "newuser@example.com"
    assert created.role == "User"
    assert created.department_id is None
    assert created.is_active is True


@pytest.mark.asyncio
async def test_existing_user_skips_create(session_repo, oauth_repo, user_repo, credential_repo, cipher):
    """이미 존재하는 user는 재생성하지 않음 (created_at 변경 없음 검증)."""
    google = FakeGoogleOAuth(sub="existing_sub", email="existing@example.com")
    uc = AuthenticateUseCase(session_repo, oauth_repo, user_repo, credential_repo, cipher, google, FakeJWT())

    await uc.execute("first_code")
    user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "existing_sub")
    first_user = await user_repo.find_by_id(user_id)
    assert first_user is not None
    original_created_at = first_user.created_at

    await uc.execute("second_code")
    second_user = await user_repo.find_by_id(user_id)
    assert second_user.created_at == original_created_at, "JIT 블록이 기존 user를 재생성하면 안 됨"


@pytest.mark.asyncio
async def test_jit_falls_back_to_email_prefix_when_name_missing(
    session_repo, oauth_repo, user_repo, credential_repo, cipher
):
    """Google user_info에 name 부재 시 email local-part로 fallback."""

    class NoNameOAuth(FakeGoogleOAuth):
        async def exchange_code(self, code: str) -> dict:
            result = await super().exchange_code(code)
            result.pop("name", None)
            return result

    google = NoNameOAuth(sub="no_name_sub", email="alice.kim@example.com")
    uc = AuthenticateUseCase(session_repo, oauth_repo, user_repo, credential_repo, cipher, google, FakeJWT())

    await uc.execute("code")

    user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "no_name_sub")
    created = await user_repo.find_by_id(user_id)
    assert created.name == "alice.kim"
