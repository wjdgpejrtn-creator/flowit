"""POST /api/v1/executions/{id}/cancel|resume owner check 단위 테스트 (PR #207).

PR #207 self-review 🔴 HIGH — cancel/resume이 owner 검증 없이 Celery dispatch했음.
본 PR이 UI 활성화로 공격면 확대 → 본 PR scope에서 owner check 5줄 추가 + 테스트.

happy(own user) 202 + 타 user 403 + 미존재 404 + Celery dispatch 검증.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt as pyjwt
import pytest
from app.config import Settings
from app.dependencies.celery_client import get_celery
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_execution_repository
from app.main import create_app
from common_schemas import PermissionSource
from common_schemas.exceptions import NotFoundError
from fastapi.testclient import TestClient


@pytest.fixture
def app(env_minimum: None):
    return create_app(Settings())  # type: ignore[call-arg]


def _override_permission(app, user_id) -> PermissionSource:
    perm = PermissionSource(
        user_id=user_id,
        role="User",
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )
    app.dependency_overrides[get_permission_source] = lambda: perm
    return perm


def _bearer() -> str:
    now = datetime.now(UTC)
    return pyjwt.encode(
        {
            "sub": str(uuid4()),
            "session_hash": "dummy",
            "type": "access",
            "exp": now + timedelta(seconds=3600),
            "iat": now,
        },
        "",
        algorithm="HS256",
    )


def _fake_row(execution_id, user_id, status="running"):
    row = MagicMock()
    row.execution_id = execution_id
    row.workflow_id = uuid4()
    row.user_id = user_id
    row.status = status
    row.started_at = datetime(2026, 5, 28, 10, 0, 0, tzinfo=UTC)
    row.completed_at = None
    row.error = None
    return row


def _override_celery(app, task_id="task-xyz"):
    celery_mock = MagicMock()
    async_result = MagicMock()
    async_result.id = task_id
    celery_mock.send_task = MagicMock(return_value=async_result)
    app.dependency_overrides[get_celery] = lambda: celery_mock
    return celery_mock


@pytest.mark.parametrize("action", ["cancel", "resume"])
def test_owner_can_cancel_or_resume_own_execution(app, action) -> None:
    """본인 소유 execution은 cancel/resume 모두 202 + Celery dispatch."""
    user_id = uuid4()
    _override_permission(app, user_id)
    exec_id = uuid4()

    repo = MagicMock()
    repo.get = AsyncMock(return_value=_fake_row(exec_id, user_id))
    app.dependency_overrides[get_execution_repository] = lambda: repo
    celery_mock = _override_celery(app)

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/executions/{exec_id}/{action}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["execution_id"] == str(exec_id)
    assert body["action"] == action
    assert body["task_id"] == "task-xyz"
    celery_mock.send_task.assert_called_once()
    repo.get.assert_awaited_once_with(exec_id)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("action", ["cancel", "resume"])
def test_other_user_cancel_or_resume_returns_403(app, action) -> None:
    """타 user 소유 execution 호출 시 403 + Celery dispatch 안 됨 (공격면 차단)."""
    requester_id = uuid4()
    owner_id = uuid4()
    _override_permission(app, requester_id)
    exec_id = uuid4()

    repo = MagicMock()
    repo.get = AsyncMock(return_value=_fake_row(exec_id, owner_id))
    app.dependency_overrides[get_execution_repository] = lambda: repo
    celery_mock = _override_celery(app)

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/executions/{exec_id}/{action}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 403
    assert "another user" in resp.json()["detail"].lower()
    celery_mock.send_task.assert_not_called()
    app.dependency_overrides.clear()


@pytest.mark.parametrize("action", ["cancel", "resume"])
def test_missing_execution_returns_404(app, action) -> None:
    """미존재 execution은 404 + Celery dispatch 안 됨."""
    user_id = uuid4()
    _override_permission(app, user_id)
    exec_id = uuid4()

    repo = MagicMock()
    repo.get = AsyncMock(side_effect=NotFoundError(f"Execution not found: {exec_id}", code="E-EXEC-001"))
    app.dependency_overrides[get_execution_repository] = lambda: repo
    celery_mock = _override_celery(app)

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/executions/{exec_id}/{action}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 404
    celery_mock.send_task.assert_not_called()
    app.dependency_overrides.clear()
