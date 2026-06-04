from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt as pyjwt
import pytest
from app.config import Settings
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_execution_repository
from app.main import create_app
from common_schemas import PermissionSource
from common_schemas.exceptions import NotFoundError
from fastapi.testclient import TestClient


@pytest.fixture
def app(env_minimum: None):
    return create_app(Settings())  # type: ignore[call-arg]


def _override_permission(app, user_id):
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


def _bearer():
    now = datetime.now(UTC)
    return pyjwt.encode(
        {"sub": str(uuid4()), "session_hash": "h", "type": "access",
         "exp": now + timedelta(seconds=3600), "iat": now},
        "test-jwt-secret-key-min-32-bytes",
        algorithm="HS256",
    )


def _fake_row(execution_id, workflow_id, user_id, status="running", completed_at=None, error=None):
    row = MagicMock()
    row.execution_id = execution_id
    row.workflow_id = workflow_id
    row.user_id = user_id
    row.status = status
    row.started_at = datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC)
    row.completed_at = completed_at
    row.error = error
    return row


def test_get_execution_returns_running_with_summary(app) -> None:
    user_id = uuid4()
    _override_permission(app, user_id)
    exec_id, wf_id = uuid4(), uuid4()

    repo = MagicMock()
    repo.get = AsyncMock(return_value=_fake_row(exec_id, wf_id, user_id, status="running"))
    repo.get_node_states_summary = AsyncMock(return_value={"succeeded": 2, "running": 1})
    app.dependency_overrides[get_execution_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(
        f"/api/v1/executions/{exec_id}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["execution_id"] == str(exec_id)
    assert body["workflow_id"] == str(wf_id)
    assert body["status"] == "running"
    assert body["finished_at"] is None
    assert body["error"] is None
    assert body["node_states_summary"] == {"succeeded": 2, "running": 1}
    assert body["last_event"] is None
    assert body["outputs"] is None

    app.dependency_overrides.clear()


def test_get_execution_returns_completed_with_finished_at(app) -> None:
    user_id = uuid4()
    _override_permission(app, user_id)
    exec_id, wf_id = uuid4(), uuid4()
    completed = datetime(2026, 5, 25, 10, 5, 0, tzinfo=UTC)

    repo = MagicMock()
    repo.get = AsyncMock(return_value=_fake_row(
        exec_id, wf_id, user_id, status="completed", completed_at=completed,
    ))
    repo.get_node_states_summary = AsyncMock(return_value={"succeeded": 3})
    app.dependency_overrides[get_execution_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(
        f"/api/v1/executions/{exec_id}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["finished_at"] is not None
    assert body["error"] is None

    app.dependency_overrides.clear()


def test_get_execution_failed_includes_error(app) -> None:
    user_id = uuid4()
    _override_permission(app, user_id)
    exec_id, wf_id = uuid4(), uuid4()

    repo = MagicMock()
    repo.get = AsyncMock(return_value=_fake_row(
        exec_id, wf_id, user_id, status="failed",
        completed_at=datetime(2026, 5, 25, 10, 3, 0, tzinfo=UTC),
        error="node X timed out",
    ))
    repo.get_node_states_summary = AsyncMock(return_value={"succeeded": 1, "failed": 1})
    app.dependency_overrides[get_execution_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(
        f"/api/v1/executions/{exec_id}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error"] == "node X timed out"
    assert body["node_states_summary"] == {"succeeded": 1, "failed": 1}

    app.dependency_overrides.clear()


def test_get_execution_empty_summary_when_worker_not_started(app) -> None:
    user_id = uuid4()
    _override_permission(app, user_id)
    exec_id, wf_id = uuid4(), uuid4()

    repo = MagicMock()
    repo.get = AsyncMock(return_value=_fake_row(exec_id, wf_id, user_id, status="pending"))
    repo.get_node_states_summary = AsyncMock(return_value={})
    app.dependency_overrides[get_execution_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(
        f"/api/v1/executions/{exec_id}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 200
    assert resp.json()["node_states_summary"] == {}

    app.dependency_overrides.clear()


def test_get_execution_not_found_returns_404(app) -> None:
    _override_permission(app, uuid4())
    exec_id = uuid4()

    repo = MagicMock()
    repo.get = AsyncMock(side_effect=NotFoundError(f"Execution not found: {exec_id}", code="E-EXEC-001"))
    app.dependency_overrides[get_execution_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(
        f"/api/v1/executions/{exec_id}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 404
    app.dependency_overrides.clear()


def test_get_execution_other_user_returns_403(app) -> None:
    me, other = uuid4(), uuid4()
    _override_permission(app, me)
    exec_id, wf_id = uuid4(), uuid4()

    repo = MagicMock()
    repo.get = AsyncMock(return_value=_fake_row(exec_id, wf_id, other, status="running"))
    app.dependency_overrides[get_execution_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(
        f"/api/v1/executions/{exec_id}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 403
    app.dependency_overrides.clear()
