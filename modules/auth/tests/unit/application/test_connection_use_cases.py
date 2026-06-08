import uuid

import pytest
from auth.application.use_cases.complete_connection_use_case import CompleteConnectionUseCase
from auth.application.use_cases.revoke_connection_use_case import RevokeConnectionUseCase
from auth.application.use_cases.start_connection_authorize_use_case import StartConnectionAuthorizeUseCase


class FakeOAuth:
    def __init__(self, sub: str = "sub1", email: str = "u@x.com", access: str = "tok") -> None:
        self._sub, self._email, self._access = sub, email, access

    def authorization_url(self, state: str, scopes: list[str] | None = None) -> str:
        return f"https://accounts.google.com/auth?state={state}&scope={' '.join(scopes or [])}"

    async def exchange_code(self, code: str) -> dict:
        return {
            "sub": self._sub,
            "email": self._email,
            "access_token": self._access,
            "refresh_token": "refresh",
            "scopes": ["openid", "email", "https://www.googleapis.com/auth/spreadsheets"],
        }


# ── Start ──────────────────────────────────────────────────────────────────


def test_start_authorize_builds_url_with_service_scopes():
    url = StartConnectionAuthorizeUseCase(FakeOAuth()).build_authorization_url("google", "state1")
    assert "state=state1" in url
    assert "spreadsheets" in url  # connection scope 포함 (로그인 신원 scope와 분리)


def test_start_authorize_rejects_unsupported_service():
    with pytest.raises(ValueError):
        StartConnectionAuthorizeUseCase(FakeOAuth()).build_authorization_url("notion", "s")


# ── Complete ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_connection_creates_with_account(oauth_repo, credential_repo, cipher):
    uc = CompleteConnectionUseCase(oauth_repo, credential_repo, cipher, FakeOAuth(sub="sub1", email="a@b.com"))
    user_id = uuid.uuid4()

    conn = await uc.execute(user_id, "google", "code")

    assert conn.service == "google"
    assert conn.account_id == "sub1"
    assert conn.display_name == "a@b.com"
    assert conn.access_token_encrypted != b"tok"  # 암호화 저장
    assert await oauth_repo.get_active_for_user(user_id, "google") is not None


@pytest.mark.asyncio
async def test_complete_connection_upsert_no_duplicate(oauth_repo, credential_repo, cipher):
    user_id = uuid.uuid4()
    await CompleteConnectionUseCase(oauth_repo, credential_repo, cipher, FakeOAuth(access="tok1")).execute(
        user_id, "google", "c1"
    )
    await CompleteConnectionUseCase(oauth_repo, credential_repo, cipher, FakeOAuth(access="tok2")).execute(
        user_id, "google", "c2"
    )

    googles = [c for c in await oauth_repo.list_for_user(user_id) if c.service == "google"]
    assert len(googles) == 1  # ④ upsert — active row 미증식


# ── Revoke ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_connection(oauth_repo):
    user_id = uuid.uuid4()
    await oauth_repo.create(user_id, "google", {"access_token_encrypted": b"x", "scopes": []})

    assert await RevokeConnectionUseCase(oauth_repo).execute(user_id, "google") is True
    assert await oauth_repo.get_active_for_user(user_id, "google") is None


@pytest.mark.asyncio
async def test_revoke_connection_missing_is_idempotent(oauth_repo):
    assert await RevokeConnectionUseCase(oauth_repo).execute(uuid.uuid4(), "google") is False
