"""GET /api/v1/workflows/{workflow_id}/executions/latest 단위 테스트 (PR #207).

happy path + 실행 0건(null 응답) + 타 user execution 격리 검증.
패턴: test_routes_executions_get.py와 동일 (mock repo + permission override).
"""
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


def _fake_row(execution_id, workflow_id, user_id, status="running", completed_at=None, error=None):
    row = MagicMock()
    row.execution_id = execution_id
    row.workflow_id = workflow_id
    row.user_id = user_id
    row.status = status
    row.started_at = datetime(2026, 5, 28, 10, 0, 0, tzinfo=UTC)
    row.completed_at = completed_at
    row.error = error
    row.node_results = [
        {"node_instance_id": str(uuid4()), "status": "succeeded", "attempt": 0, "last_error": None},
        {"node_instance_id": str(uuid4()), "status": "running", "attempt": 0, "last_error": None},
    ]
    return row


def test_latest_execution_returns_running_with_node_results(app) -> None:
    """워크플로우의 가장 최근 execution이 running일 때 200 + 전체 필드 반환."""
    user_id = uuid4()
    _override_permission(app, user_id)
    workflow_id, execution_id = uuid4(), uuid4()

    repo = MagicMock()
    repo.get_latest_by_workflow_id = AsyncMock(
        return_value=_fake_row(execution_id, workflow_id, user_id, status="running")
    )
    repo.get_node_states_summary = AsyncMock(return_value={"succeeded": 1, "running": 1})
    app.dependency_overrides[get_execution_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(
        f"/api/v1/workflows/{workflow_id}/executions/latest",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body is not None
    assert body["execution_id"] == str(execution_id)
    assert body["workflow_id"] == str(workflow_id)
    assert body["status"] == "running"
    assert body["finished_at"] is None
    assert body["error"] is None
    assert body["node_states_summary"] == {"succeeded": 1, "running": 1}
    assert len(body["node_results"]) == 2

    repo.get_latest_by_workflow_id.assert_awaited_once_with(workflow_id, user_id)
    app.dependency_overrides.clear()


def test_latest_execution_returns_null_when_no_execution(app) -> None:
    """워크플로우는 있지만 실행 이력 0건이면 200 + body=null (404 아님)."""
    user_id = uuid4()
    _override_permission(app, user_id)
    workflow_id = uuid4()

    repo = MagicMock()
    repo.get_latest_by_workflow_id = AsyncMock(return_value=None)
    # 호출되지 않아야 함 (row가 None이라 summary 조회 skip)
    repo.get_node_states_summary = AsyncMock(return_value={})
    app.dependency_overrides[get_execution_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(
        f"/api/v1/workflows/{workflow_id}/executions/latest",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 200
    assert resp.json() is None
    repo.get_node_states_summary.assert_not_awaited()
    app.dependency_overrides.clear()


def test_latest_execution_returns_completed_with_finished_at(app) -> None:
    """완료된 execution은 finished_at + node_states_summary 정합 반환."""
    user_id = uuid4()
    _override_permission(app, user_id)
    workflow_id, execution_id = uuid4(), uuid4()
    completed_at = datetime(2026, 5, 28, 10, 5, 30, tzinfo=UTC)

    repo = MagicMock()
    repo.get_latest_by_workflow_id = AsyncMock(
        return_value=_fake_row(
            execution_id, workflow_id, user_id, status="completed", completed_at=completed_at
        )
    )
    repo.get_node_states_summary = AsyncMock(return_value={"succeeded": 3, "cancelled": 1})
    app.dependency_overrides[get_execution_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(
        f"/api/v1/workflows/{workflow_id}/executions/latest",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["finished_at"] is not None
    assert body["node_states_summary"] == {"succeeded": 3, "cancelled": 1}
    app.dependency_overrides.clear()
