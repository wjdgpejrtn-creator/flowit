"""Smoke tests for ORM model CRUD operations."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.models.user import UserModel
from src.models.workflow import WorkflowModel


@pytest.mark.asyncio
async def test_create_user(db_session):
    user = UserModel(
        email="test@example.com",
        name="Test User",
        role="user",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.is_active is True


@pytest.mark.asyncio
async def test_create_workflow(db_session):
    user = UserModel(email="owner@example.com", name="Owner")
    db_session.add(user)
    await db_session.flush()

    workflow = WorkflowModel(
        user_id=user.id,
        name="Test Workflow",
        scope="private",
        nodes=[{"id": "n1", "type": "trigger_manual"}],
        connections=[],
    )
    db_session.add(workflow)
    await db_session.flush()
    await db_session.refresh(workflow)

    assert workflow.id is not None
    assert workflow.version == 1
    assert workflow.is_draft is True
