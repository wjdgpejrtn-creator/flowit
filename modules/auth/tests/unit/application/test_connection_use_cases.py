import uuid

import pytest
from auth.application.use_cases.complete_connection_use_case import CompleteConnectionUseCase
from auth.application.use_cases.revoke_connection_use_case import RevokeConnectionUseCase
from auth.application.use_cases.start_connection_authorize_use_case import StartConnectionAuthorizeUseCase


class FakeOAuth:
    def __init__(self, sub: str = "sub1", email: str = "u@x.com", access: str = "tok") -> None:
        self._sub, self._email, self._access = sub, email, access

    def authorization_url(self, state: str, scopes: list[str] | None = None, redirect_uri: str | None = None) -> str:
        return (
            f"https://accounts.google.com/auth?state={state}"
            f"&scope={' '.join(scopes or [])}&redirect_uri={redirect_uri or ''}"
        )

    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> dict:
        return {
            "sub": self._sub,
            "email": self._email,
            "access_token": self._access,
            "refresh_token": "refresh",
            "expires_in": 3600,
            "scopes": ["openid", "email", "https://www.googleapis.com/auth/spreadsheets"],
        }


# ── Start ──────────────────────────────────────────────────────────────────


def test_start_authorize_builds_url_with_service_scopes():
    url = StartConnectionAuthorizeUseCase(FakeOAuth()).build_authorization_url("google", "state1")
    assert "state=state1" in url
    assert "spreadsheets" in url  # connection scope 포함 (로그인 신원 scope와 분리)


def test_google_connection_scopes_cover_read_and_write():
    # #438 §6.6 D: read/write 양방향 노드 충족. gmail은 send+readonly 둘 다 필요
    # (gmail.send만으론 gmail_read 불가). 나머지는 broad scope가 read까지 포함.
    from auth.application.use_cases.start_connection_authorize_use_case import CONNECTION_SCOPES

    google = CONNECTION_SCOPES["google"]
    assert "https://www.googleapis.com/auth/gmail.send" in google
    assert "https://www.googleapis.com/auth/gmail.readonly" in google  # gmail_read
    assert "https://www.googleapis.com/auth/spreadsheets" in google    # sheets read+write
    assert "https://www.googleapis.com/auth/drive" in google           # drive read+upload
    assert "https://www.googleapis.com/auth/documents" in google       # docs read+write
    assert "https://www.googleapis.com/auth/calendar.events" in google # calendar read+create


def test_start_authorize_rejects_unsupported_service():
    with pytest.raises(ValueError):
        StartConnectionAuthorizeUseCase(FakeOAuth()).build_authorization_url("notion", "s")


def test_start_authorize_uses_connection_redirect_uri():
    """connection callback redirect_uri가 authorize URL에 반영 — 로그인 callback과 분리 (셀프리뷰 HIGH)."""
    redirect = "https://api.example/api/v1/connections/google/callback"
    url = StartConnectionAuthorizeUseCase(FakeOAuth()).build_authorization_url("google", "s", redirect)
    assert f"redirect_uri={redirect}" in url


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
async def test_complete_connection_persists_token_expiry(oauth_repo, credential_repo, cipher):
    """expires_in → access_token_expires_at(now+expires_in) 영속화 (#452 ②)."""
    from datetime import UTC, datetime

    uc = CompleteConnectionUseCase(oauth_repo, credential_repo, cipher, FakeOAuth())
    user_id = uuid.uuid4()

    conn = await uc.execute(user_id, "google", "code")

    assert conn.access_token_expires_at is not None
    assert conn.access_token_expires_at > datetime.now(UTC)  # 미래 만료시각


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
