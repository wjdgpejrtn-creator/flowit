from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt as pyjwt
import pytest
from app.config import Settings
from app.dependencies.celery_client import get_celery
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_execution_repository, get_workflow_repository
from app.dependencies.use_cases import get_autobind_connections_use_case
from app.main import create_app
from common_schemas import PermissionSource, WorkflowSchema
from fastapi.testclient import TestClient


@pytest.fixture
def app(env_minimum: None):
    _app = create_app(Settings())  # type: ignore[call-arg]
    # execute 라우트도 _service(→autobinder→oauth/node_def repo→DB)를 주입받으므로, DB state 없는
    # 단위 테스트에서는 passthrough autobinder로 기본 오버라이드한다.
    _app.dependency_overrides[get_autobind_connections_use_case] = (
        lambda: _PassthroughAutobinder()
    )
    return _app


class _PassthroughAutobinder:
    async def execute(self, workflow: WorkflowSchema, user_id) -> WorkflowSchema:
        return workflow


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


def _fake_workflow(wf_id):
    return WorkflowSchema(
        workflow_id=wf_id,
        owner_user_id=uuid4(),
        name="wf",
        scope="private",
        is_draft=False,
        nodes=[],
        connections=[],
    )


def test_execute_dispatches_celery_task_with_context(app) -> None:
    user_id = uuid4()
    _override_permission(app, user_id)
    wf_id = uuid4()

    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=_fake_workflow(wf_id))
    app.dependency_overrides[get_workflow_repository] = lambda: repo

    fake_async = MagicMock(id="celery-task-id-123")
    fake_celery = MagicMock()
    fake_celery.send_task = MagicMock(return_value=fake_async)
    app.dependency_overrides[get_celery] = lambda: fake_celery

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/workflows/{wf_id}/execute",
        json={"trigger_type": "manual", "parameters": {"k": "v"}},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["task_id"] == "celery-task-id-123"

    # Celery send_task 호출 검증 — task name 문자열, args/queue
    fake_celery.send_task.assert_called_once()
    call = fake_celery.send_task.call_args
    assert call.args[0] == "execution_engine.execute_workflow"
    assert call.kwargs["queue"] == "default"
    workflow_id_arg, context_data = call.kwargs["args"]
    assert workflow_id_arg == str(wf_id)
    assert context_data["user_id"] == str(user_id)
    assert context_data["workflow_id"] == str(wf_id)
    assert context_data["trigger_type"] == "manual"
    assert context_data["parameters"] == {"k": "v"}
    assert context_data["execution_id"] == body["execution_id"]

    app.dependency_overrides.clear()


def test_execute_nonexistent_workflow_returns_404(app) -> None:
    _override_permission(app, uuid4())

    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=None)
    app.dependency_overrides[get_workflow_repository] = lambda: repo
    app.dependency_overrides[get_celery] = lambda: MagicMock()

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/workflows/{uuid4()}/execute",
        json={},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 404
    app.dependency_overrides.clear()


def test_cancel_execution_dispatches_task(app) -> None:
    user_id = uuid4()
    _override_permission(app, user_id)
    exec_id = uuid4()

    # cancel 라우트는 dispatch 전 _verify_execution_owner로 소유자를 확인 → repo.get 필요.
    repo = MagicMock()
    repo.get = AsyncMock(return_value=MagicMock(user_id=user_id))
    app.dependency_overrides[get_execution_repository] = lambda: repo

    fake_async = MagicMock(id="cancel-task-id")
    fake_celery = MagicMock()
    fake_celery.send_task = MagicMock(return_value=fake_async)
    app.dependency_overrides[get_celery] = lambda: fake_celery

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/executions/{exec_id}/cancel",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["action"] == "cancel"
    assert body["task_id"] == "cancel-task-id"
    fake_celery.send_task.assert_called_once_with(
        "execution_engine.cancel_execution",
        args=[str(exec_id)],
        queue="default",
    )
    app.dependency_overrides.clear()


def test_resume_execution_dispatches_task(app) -> None:
    user_id = uuid4()
    _override_permission(app, user_id)
    exec_id = uuid4()

    # resume 라우트도 dispatch 전 _verify_execution_owner로 소유자를 확인 → repo.get 필요.
    repo = MagicMock()
    repo.get = AsyncMock(return_value=MagicMock(user_id=user_id))
    app.dependency_overrides[get_execution_repository] = lambda: repo

    fake_async = MagicMock(id="resume-task-id")
    fake_celery = MagicMock()
    fake_celery.send_task = MagicMock(return_value=fake_async)
    app.dependency_overrides[get_celery] = lambda: fake_celery

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/executions/{exec_id}/resume",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["action"] == "resume"
    fake_celery.send_task.assert_called_once_with(
        "execution_engine.resume_execution",
        args=[str(exec_id)],
        queue="default",
    )
    app.dependency_overrides.clear()


def test_execute_without_celery_returns_503(app) -> None:
    """REDIS_URL 미설정 → get_celery가 503 raise."""
    _override_permission(app, uuid4())
    wf_id = uuid4()

    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=_fake_workflow(wf_id))
    app.dependency_overrides[get_workflow_repository] = lambda: repo
    # get_celery override 안 함 — app.state.celery는 None이라 503

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/workflows/{wf_id}/execute",
        json={},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 503
    assert "REDIS_URL" in resp.json()["detail"]

    app.dependency_overrides.clear()
