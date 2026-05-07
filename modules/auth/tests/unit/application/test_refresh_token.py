import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from auth.application.use_cases.refresh_token import RefreshTokenUseCase
from common_schemas.exceptions import AuthorizationError


class FakeJWT:
    """Simple fake JWT: encodes as 'tok:key=val,key=val', decodes back to dict."""

    def encode(self, payload: dict, ttl_seconds: int | None = None) -> str:
        parts = [f"{k}={v}" for k, v in payload.items()]
        return "tok:" + ",".join(parts)

    def decode(self, token: str) -> dict:
        if not token.startswith("tok:"):
            raise ValueError("Invalid token")
        raw = token.removeprefix("tok:")
        return dict(part.split("=", 1) for part in raw.split(","))


class BadJWT:
    def encode(self, payload: dict, ttl_seconds: int | None = None) -> str:
        return "bad"

    def decode(self, token: str) -> dict:
        raise ValueError("decode failed")


@pytest.mark.asyncio
async def test_refresh_issues_new_pair(session_repo):
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    user_id = uuid4()
    await session_repo.create(user_id, "sess_hash_1", expires_at)

    jwt = FakeJWT()
    refresh_tok = jwt.encode({"sub": str(user_id), "session_hash": "sess_hash_1", "type": "refresh"})

    uc = RefreshTokenUseCase(session_repo, jwt)
    pair = await uc.execute(refresh_tok)

    access_payload = jwt.decode(pair.access_token)
    assert access_payload["type"] == "access"
    assert access_payload["session_hash"] == "sess_hash_1"


@pytest.mark.asyncio
async def test_refresh_with_access_token_raises(session_repo):
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    user_id = uuid4()
    await session_repo.create(user_id, "sess_hash_2", expires_at)

    jwt = FakeJWT()
    access_tok = jwt.encode({"sub": str(user_id), "session_hash": "sess_hash_2", "type": "access"})

    uc = RefreshTokenUseCase(session_repo, jwt)
    with pytest.raises(AuthorizationError) as exc_info:
        await uc.execute(access_tok)
    assert exc_info.value.code == "E-AUTH-005"


@pytest.mark.asyncio
async def test_refresh_with_invalid_token_raises(session_repo):
    uc = RefreshTokenUseCase(session_repo, BadJWT())
    with pytest.raises(AuthorizationError) as exc_info:
        await uc.execute("garbage_token")
    assert exc_info.value.code == "E-AUTH-005"


@pytest.mark.asyncio
async def test_refresh_revoked_session_raises(session_repo):
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    user_id = uuid4()
    session = await session_repo.create(user_id, "sess_hash_3", expires_at)
    await session_repo.revoke(session.session_id)

    jwt = FakeJWT()
    refresh_tok = jwt.encode({"sub": str(user_id), "session_hash": "sess_hash_3", "type": "refresh"})

    uc = RefreshTokenUseCase(session_repo, jwt)
    with pytest.raises(AuthorizationError) as exc_info:
        await uc.execute(refresh_tok)
    assert exc_info.value.code == "E-AUTH-006"
