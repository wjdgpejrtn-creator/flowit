"""H-3 contract tests for SessionRepository."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.models.chat import ChatSessionModel
from src.models.user import UserModel
from src.repositories.session_repository import SessionRepository


@pytest.mark.asyncio
async def test_create_and_find_session(db_session):
    user = UserModel(email="session@test.com", name="Session User")
    db_session.add(user)
    await db_session.flush()

    repo = SessionRepository(db_session)
    session = await repo.create_session(
        user_id=user.id,
        session_hash="abc123hash",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )

    assert session.id is not None
    assert session.session_hash == "abc123hash"

    found = await repo.find_by_hash("abc123hash")
    assert found is not None
    assert found.id == session.id


@pytest.mark.asyncio
async def test_revoke_session(db_session):
    user = UserModel(email="revoke@test.com", name="Revoke User")
    db_session.add(user)
    await db_session.flush()

    repo = SessionRepository(db_session)
    session = await repo.create_session(
        user_id=user.id,
        session_hash="revoke_hash",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    await repo.revoke(session.id)

    found = await repo.find_by_hash("revoke_hash")
    assert found is None


@pytest.mark.asyncio
async def test_revoke_all_for_user(db_session):
    user = UserModel(email="revokeall@test.com", name="RevokeAll User")
    db_session.add(user)
    await db_session.flush()

    repo = SessionRepository(db_session)
    for i in range(3):
        await repo.create_session(
            user_id=user.id,
            session_hash=f"hash_{i}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

    count = await repo.revoke_all_for_user(user.id)
    assert count == 3
