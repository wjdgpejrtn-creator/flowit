import pytest
import uuid
from datetime import datetime, timezone

from auth.application.use_cases.authenticate import AuthenticateUseCase


class FakeGoogleOAuth:
    def __init__(self, sub: str = "google_sub_123", email: str = "user@example.com"):
        self._sub = sub
        self._email = email

    async def exchange_code(self, code: str) -> dict:
        return {
            "sub": self._sub,
            "email": self._email,
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
async def test_authenticate_returns_token_pair(session_repo, oauth_repo, cipher):
    uc = AuthenticateUseCase(session_repo, oauth_repo, cipher, FakeGoogleOAuth(), FakeJWT())
    pair = await uc.execute("auth_code_abc")

    assert pair.access_token.startswith("tok:")
    assert pair.refresh_token.startswith("tok:")
    assert pair.token_type == "Bearer"


@pytest.mark.asyncio
async def test_authenticate_derives_deterministic_user_id(session_repo, oauth_repo, cipher):
    google = FakeGoogleOAuth(sub="stable_sub_999")
    jwt = FakeJWT()
    uc = AuthenticateUseCase(session_repo, oauth_repo, cipher, google, jwt)

    pair1 = await uc.execute("code_1")
    pair2 = await uc.execute("code_2")

    payload1 = jwt.decode(pair1.access_token)
    payload2 = jwt.decode(pair2.access_token)

    expected_user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "stable_sub_999"))
    assert payload1["sub"] == expected_user_id
    assert payload2["sub"] == expected_user_id


@pytest.mark.asyncio
async def test_authenticate_stores_encrypted_token(session_repo, oauth_repo, cipher):
    google = FakeGoogleOAuth(sub="sub_encrypt_test")
    uc = AuthenticateUseCase(session_repo, oauth_repo, cipher, google, FakeJWT())
    await uc.execute("code_xyz")

    user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "sub_encrypt_test")
    conn = await oauth_repo.get_active_for_user(user_id, "google")

    assert conn.encrypted_access_token != b"goog_access_token"
    assert cipher.decrypt(conn.encrypted_access_token) == b"goog_access_token"


@pytest.mark.asyncio
async def test_authenticate_second_login_updates_tokens(session_repo, oauth_repo, cipher):
    google_first = FakeGoogleOAuth(sub="sub_reauth")
    uc = AuthenticateUseCase(session_repo, oauth_repo, cipher, google_first, FakeJWT())
    await uc.execute("first_code")

    class FakeGoogleOAuthV2(FakeGoogleOAuth):
        async def exchange_code(self, code: str) -> dict:
            result = await super().exchange_code(code)
            result["access_token"] = "new_access_token"
            return result

    uc2 = AuthenticateUseCase(session_repo, oauth_repo, cipher, FakeGoogleOAuthV2(sub="sub_reauth"), FakeJWT())
    await uc2.execute("second_code")

    user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "sub_reauth")
    conn = await oauth_repo.get_active_for_user(user_id, "google")
    assert cipher.decrypt(conn.encrypted_access_token) == b"new_access_token"
