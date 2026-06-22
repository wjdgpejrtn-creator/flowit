from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt as pyjwt
import pytest
from app.config import Settings
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_workflow_repository
from app.dependencies.use_cases import (
    get_autobind_connections_use_case,
    get_validate_graph_use_case,
)
from app.main import create_app
from common_schemas import (
    PermissionSource,
    ValidationErrorResponse,
    WorkflowSchema,
)
from fastapi.testclient import TestClient


class _PassthroughAutobinder:
    """노드 connection 선바인딩 no-op 페이크 — 단위 테스트에서 DB 의존 회피."""

    async def execute(self, workflow: WorkflowSchema, user_id) -> WorkflowSchema:
        return workflow


@pytest.fixture
def app(env_minimum: None):
    _app = create_app(Settings())  # type: ignore[call-arg]
    # _service·validate가 autobinder를 주입받으며, 실 구현은 oauth/node_def repo(→DB)를 탄다.
    # 라우터 단위 테스트는 DB state가 없으므로 passthrough로 기본 오버라이드(개별 테스트가 필요 시 교체).
    _app.dependency_overrides[get_autobind_connections_use_case] = lambda: _PassthroughAutobinder()
    return _app


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
        "test-jwt-secret-key-min-32-bytes",
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
    _override_permission(app, user_id)

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


def test_save_applies_autobinder_result(app) -> None:
    """save가 autobinder.execute 결과(선바인딩된 워크플로우)를 repo에 저장하는지 검증.

    편집 페이지에서 추가/변경한 노드의 미바인딩 connection을 저장 시점에 자동 선바인딩 →
    E_MISSING_CONNECTION 방지. autobinder가 credential_ids를 채운 결과가 그대로 영속화돼야 한다.
    """
    user_id = uuid4()
    _override_permission(app, user_id)

    repo = MagicMock()
    repo.save = AsyncMock(side_effect=lambda wf: wf.workflow_id)
    repo.find_by_id = AsyncMock(side_effect=lambda wid: WorkflowSchema(
        workflow_id=wid, owner_user_id=user_id, name="x", scope="private",
        is_draft=True, nodes=[], connections=[],
    ))
    app.dependency_overrides[get_workflow_repository] = lambda: repo

    class _SpyAutobinder:
        def __init__(self) -> None:
            self.called_with = None

        async def execute(self, workflow: WorkflowSchema, uid) -> WorkflowSchema:
            self.called_with = (workflow, uid)
            # credential_ids를 채워 반환 — 이 결과가 저장돼야 함
            return workflow.model_copy(update={"name": "bound"})

    spy = _SpyAutobinder()
    app.dependency_overrides[get_autobind_connections_use_case] = lambda: spy

    client = TestClient(app)
    resp = client.post(
        "/api/v1/workflows", json=_empty_workflow(),
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 201
    # autobinder가 user_id와 함께 호출됨
    assert spy.called_with is not None
    assert spy.called_with[1] == user_id
    # repo.save가 autobinder 결과(name="bound")를 받음
    saved_wf: WorkflowSchema = repo.save.await_args.args[0]
    assert saved_wf.name == "bound"

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
    list_resp = client.get("/api/v1/workflows")
    assert list_resp.status_code == 401


# ── GET /api/v1/workflows (목록 조회) ───────────────────────────────────────


def _wf(workflow_id, owner_user_id, name: str = "wf") -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=workflow_id,
        owner_user_id=owner_user_id,
        name=name,
        scope="private",
        is_draft=False,
        nodes=[],
        connections=[],
    )


def test_list_workflows_returns_owned(app) -> None:
    user_id = uuid4()
    _override_permission(app, user_id)
    wf1, wf2 = uuid4(), uuid4()

    repo = MagicMock()
    repo.list_by_owner = AsyncMock(return_value=[_wf(wf1, user_id, "first"), _wf(wf2, user_id, "second")])
    app.dependency_overrides[get_workflow_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get("/api/v1/workflows", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert {item["workflow_id"] for item in body} == {str(wf1), str(wf2)}
    repo.list_by_owner.assert_awaited_once_with(owner_user_id=user_id, limit=50, offset=0)

    app.dependency_overrides.clear()


def test_list_workflows_empty(app) -> None:
    _override_permission(app, uuid4())
    repo = MagicMock()
    repo.list_by_owner = AsyncMock(return_value=[])
    app.dependency_overrides[get_workflow_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get("/api/v1/workflows", headers={"Authorization": f"Bearer {_bearer()}"})

    assert resp.status_code == 200
    assert resp.json() == []

    app.dependency_overrides.clear()


def test_list_workflows_forwards_pagination(app) -> None:
    user_id = uuid4()
    _override_permission(app, user_id)
    repo = MagicMock()
    repo.list_by_owner = AsyncMock(return_value=[])
    app.dependency_overrides[get_workflow_repository] = lambda: repo

    client = TestClient(app)
    resp = client.get(
        "/api/v1/workflows?limit=10&offset=20",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 200
    repo.list_by_owner.assert_awaited_once_with(owner_user_id=user_id, limit=10, offset=20)

    app.dependency_overrides.clear()


def test_list_workflows_limit_bounds(app) -> None:
    """limit ∈ [1, 100], offset ≥ 0 — FastAPI Query 검증 → 422."""
    _override_permission(app, uuid4())
    repo = MagicMock()
    repo.list_by_owner = AsyncMock(return_value=[])
    app.dependency_overrides[get_workflow_repository] = lambda: repo

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_bearer()}"}
    assert client.get("/api/v1/workflows?limit=0", headers=headers).status_code == 422
    assert client.get("/api/v1/workflows?limit=101", headers=headers).status_code == 422
    assert client.get("/api/v1/workflows?offset=-1", headers=headers).status_code == 422
    repo.list_by_owner.assert_not_awaited()

    app.dependency_overrides.clear()
