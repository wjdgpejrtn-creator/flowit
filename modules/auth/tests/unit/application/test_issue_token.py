from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from auth.application.use_cases.issue_token import IssueTokenUseCase
from common_schemas.exceptions import AuthorizationError


class FakeJWT:
    def encode(self, payload: dict, ttl_seconds: int | None = None) -> str:
        parts = [f"{k}={v}" for k, v in payload.items()]
        return "tok:" + ",".join(parts)

    def decode(self, token: str) -> dict:
        raw = token.removeprefix("tok:")
        return dict(part.split("=", 1) for part in raw.split(","))


@pytest.mark.asyncio
async def test_issue_token_returns_token_pair(session_repo):
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    await session_repo.create(uuid4(), "hash_abc", expires_at=expires_at)

    uc = IssueTokenUseCase(session_repo, FakeJWT())
    pair = await uc.execute("hash_abc")

    assert pair.access_token.startswith("tok:")
    assert pair.refresh_token.startswith("tok:")
    assert pair.token_type == "Bearer"


@pytest.mark.asyncio
async def test_issue_token_encodes_correct_type(session_repo):
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    await session_repo.create(uuid4(), "hash_xyz", expires_at=expires_at)

    jwt = FakeJWT()
    uc = IssueTokenUseCase(session_repo, jwt)
    pair = await uc.execute("hash_xyz")

    access_payload = jwt.decode(pair.access_token)
    refresh_payload = jwt.decode(pair.refresh_token)

    assert access_payload["type"] == "access"
    assert refresh_payload["type"] == "refresh"


@pytest.mark.asyncio
async def test_issue_token_revoked_session_raises(session_repo):
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    session = await session_repo.create(uuid4(), "hash_revoked", expires_at=expires_at)
    await session_repo.revoke(session.session_id)

    uc = IssueTokenUseCase(session_repo, FakeJWT())
    with pytest.raises(AuthorizationError) as exc_info:
        await uc.execute("hash_revoked")
    assert exc_info.value.code == "E-AUTH-003"


@pytest.mark.asyncio
async def test_issue_token_expired_session_raises(session_repo):
    expired_at = datetime.now(UTC) - timedelta(seconds=1)
    await session_repo.create(uuid4(), "hash_expired", expires_at=expired_at)

    uc = IssueTokenUseCase(session_repo, FakeJWT())
    with pytest.raises(AuthorizationError) as exc_info:
        await uc.execute("hash_expired")
    assert exc_info.value.code == "E-AUTH-003"
