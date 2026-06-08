import uuid

import pytest
from auth.application.use_cases.list_connections_use_case import ListConnectionsUseCase


@pytest.mark.asyncio
async def test_list_connections_returns_active_with_display(oauth_repo):
    user_id = uuid.uuid4()
    await oauth_repo.create(
        user_id, "google", {"access_token_encrypted": b"a", "scopes": [], "display_name": "u@x.com"}
    )
    await oauth_repo.create(
        user_id, "slack", {"access_token_encrypted": b"b", "scopes": [], "display_name": "flowit-team"}
    )

    result = await ListConnectionsUseCase(oauth_repo).execute(user_id)

    by_service = {c.service: c for c in result}
    assert by_service["google"].display == "u@x.com"
    assert by_service["slack"].display == "flowit-team"
    assert all(c.connected and c.status == "connected" for c in result)


@pytest.mark.asyncio
async def test_list_connections_scoped_to_user(oauth_repo):
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    await oauth_repo.create(u1, "google", {"access_token_encrypted": b"a", "scopes": []})
    await oauth_repo.create(u2, "slack", {"access_token_encrypted": b"b", "scopes": []})

    result = await ListConnectionsUseCase(oauth_repo).execute(u1)

    assert [c.service for c in result] == ["google"]


@pytest.mark.asyncio
async def test_list_connections_excludes_revoked(oauth_repo):
    user_id = uuid.uuid4()
    conn = await oauth_repo.create(user_id, "google", {"access_token_encrypted": b"a", "scopes": []})
    await oauth_repo.revoke(conn.credential_id)

    result = await ListConnectionsUseCase(oauth_repo).execute(user_id)

    assert result == []


@pytest.mark.asyncio
async def test_list_connections_display_none_when_unset(oauth_repo):
    """display_name 미확보(NULL) 시 None — connected 여부는 그대로 반영."""
    user_id = uuid.uuid4()
    await oauth_repo.create(user_id, "google", {"access_token_encrypted": b"a", "scopes": []})

    result = await ListConnectionsUseCase(oauth_repo).execute(user_id)

    assert result[0].display is None
    assert result[0].connected is True
