"""PR2-B: OAuthConnectionResolver — auth.OAuthConnectionRepository Facade."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from auth.domain.entities.oauth_connection import OAuthConnection
from auth.domain.ports.oauth_connection_repository import OAuthConnectionRepository

from ai_agent.adapters.connection_resolver_adapter import OAuthConnectionResolver


def _conn(credential_id, service="google", is_active=True) -> OAuthConnection:
    return OAuthConnection(
        oauth_id=uuid4(),
        user_id=uuid4(),
        service=service,
        credential_id=credential_id,
        access_token_encrypted=b"x",
        scopes=["email"],
        is_active=is_active,
        connected_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_returns_credential_id_when_active_connection_exists():
    cred = uuid4()
    repo = AsyncMock(spec=OAuthConnectionRepository)
    repo.get_active_for_user = AsyncMock(return_value=_conn(cred))
    resolver = OAuthConnectionResolver(repo)

    out = await resolver.resolve(uuid4(), "google")
    assert out == cred


@pytest.mark.asyncio
async def test_returns_none_when_no_connection():
    repo = AsyncMock(spec=OAuthConnectionRepository)
    repo.get_active_for_user = AsyncMock(return_value=None)
    resolver = OAuthConnectionResolver(repo)

    assert await resolver.resolve(uuid4(), "slack") is None


@pytest.mark.asyncio
async def test_returns_none_when_connection_inactive():
    repo = AsyncMock(spec=OAuthConnectionRepository)
    repo.get_active_for_user = AsyncMock(return_value=_conn(uuid4(), is_active=False))
    resolver = OAuthConnectionResolver(repo)

    assert await resolver.resolve(uuid4(), "google") is None
