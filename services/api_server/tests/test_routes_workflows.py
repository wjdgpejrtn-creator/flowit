from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_workflow_repository
from app.dependencies.use_cases import get_validate_graph_use_case
from app.main import create_app
from common_schemas import (
    PermissionSource,
    ValidationErrorResponse,
    WorkflowSchema,
)


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


def _empty_workflow(workflow_id=None) -> dict:
    return {
        "workflow_id": str(workflow_id or uuid4()),
        "name": "test wf",
        "scope": "private",
        "is_draft": True,
        "nodes": [],
        "connections": [],
    }


def test_create_workflow_injects_owner_user_id(app) -> None:
    """PR #66 v0.3.0 — owner_user_id 명시 주입 검증."""
    user_id = uuid4()
    perm = _override_permission(app, user_id)

    repo = MagicMock()
    saved_workflows: dict = {}

    async def fake_save(wf: WorkflowSchema):
        saved_workflows[wf.workflow_id] = wf
        return wf.workflow_id

    async def fake_find(workflow_id):
        return saved_workflows.get(workflow_id)

    repo.save = AsyncMock(side_effect=fake_save)
    repo.find_by_id = AsyncMock(side_effect=fake_find)
    app.dependency_overrides[get_workflow_repository] = lambda: repo

    body = _empty_workflow()
    client = TestClient(app)
    resp = client.post("/api/v1/workflows", json=body, headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 201
    returned = resp.json()
    assert returned["owner_user_id"] == str(user_id)  # ← 라우터가 명시 주입 검증
    assert returned["workflow_id"] == body["workflow_id"]

    # Repository.save가 owner_user_id 채워진 도메인 객체 받음
    saved_call = repo.save.await_args
    saved_wf: WorkflowSchema = saved_call.args[0]
    assert saved_wf.owner_user_id == user_id

    app.dependency_overrides.clear()


def test_get_workflow_returns_existing(app) -> None:
    _override_permission(app, uuid4())
    wf_id = uuid4()

    repo = MagicMock()
    repo.find_by_id = AsyncMock(
        return_value=WorkflowSchema(
            workflow_id=wf_id,
            owner_user_id=uuid4(),
            name="existing",
            scope="private",
            is_draft=False,
            nodes=[],
            connections=[],
        )
    )
    app.dependency_overrides[get_workflow_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(f"/api/v1/workflows/{wf_id}", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 200
    assert resp.json()["workflow_id"] == str(wf_id)
    repo.find_by_id.assert_awaited_once_with(wf_id)

    app.dependency_overrides.clear()


def test_get_workflow_not_found(app) -> None:
    _override_permission(app, uuid4())

    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=None)
    app.dependency_overrides[get_workflow_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(f"/api/v1/workflows/{uuid4()}", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "E-WF-001"

    app.dependency_overrides.clear()


def test_put_workflow_path_body_mismatch_rejected(app) -> None:
    _override_permission(app, uuid4())
    repo = MagicMock()
    app.dependency_overrides[get_workflow_repository] = lambda: repo

    body = _empty_workflow()  # body의 workflow_id는 새 uuid
    different_path_id = uuid4()  # path의 workflow_id 다름

    client = TestClient(app)
    resp = client.put(
        f"/api/v1/workflows/{different_path_id}",
        json=body,
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 400
    assert "Path workflow_id" in resp.json()["detail"]

    app.dependency_overrides.clear()


def test_validate_workflow_returns_validation_result(app) -> None:
    _override_permission(app, uuid4())
    wf_id = uuid4()

    repo = MagicMock()
    repo.find_by_id = AsyncMock(
        return_value=WorkflowSchema(
            workflow_id=wf_id,
            owner_user_id=uuid4(),
            name="wf",
            scope="private",
            is_draft=True,
            nodes=[],
            connections=[],
        )
    )
    app.dependency_overrides[get_workflow_repository] = lambda: repo

    fake_use_case = MagicMock()
    fake_use_case.execute = AsyncMock(
        return_value=ValidationErrorResponse(validation_status="passed", errors=[])
    )
    app.dependency_overrides[get_validate_graph_use_case] = lambda: fake_use_case

    client = TestClient(app)
    resp = client.post(
        f"/api/v1/workflows/{wf_id}/validate", headers={"Authorization": f"Bearer {_bearer()}"}
    )

    assert resp.status_code == 200
    assert resp.json()["validation_status"] == "passed"
    fake_use_case.execute.assert_awaited_once()

    app.dependency_overrides.clear()


def test_workflows_require_bearer(app) -> None:
    client = TestClient(app)
    resp = client.get(f"/api/v1/workflows/{uuid4()}")
    assert resp.status_code == 401
