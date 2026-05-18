from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_node_definition_repository
from app.main import create_app
from common_schemas import PermissionSource
from common_schemas.enums import RiskLevel
from nodes_graph.domain.entities.node_definition import NodeDefinition


@pytest.fixture
def app(env_minimum: None):
    return create_app(Settings())  # type: ignore[call-arg]


def _fake_definition(node_type: str, *, is_mvp: bool = True, risk: RiskLevel = RiskLevel.LOW) -> NodeDefinition:
    return NodeDefinition(
        node_id=uuid4(),
        node_type=node_type,
        name=node_type.replace("_", " ").title(),
        category="api",
        version="1.0.0",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        parameter_schema={},
        risk_level=risk,
        required_connections=[],
        description=f"{node_type} node",
        is_mvp=is_mvp,
        embedding=None,
    )


def _override_permission(app, *, role: str = "User") -> None:
    """AuthMiddleware 우회 — PermissionSource를 직접 주입."""
    fake_permission = PermissionSource(
        user_id=uuid4(),
        role=role,  # type: ignore[arg-type]
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )
    app.dependency_overrides[get_permission_source] = lambda: fake_permission


def _bearer_token() -> str:
    """AuthMiddleware 통과용 dummy JWT (env_minimum의 빈 JWT_SECRET_KEY)."""
    now = datetime.now(UTC)
    return pyjwt.encode(
        {
            "sub": str(uuid4()),
            "session_hash": "dummy-hash",
            "type": "access",
            "exp": now + timedelta(seconds=3600),
            "iat": now,
        },
        "",
        algorithm="HS256",
    )


def test_catalog_returns_list(app) -> None:
    fake_repo = MagicMock()
    fake_repo.list_all = AsyncMock(
        return_value=[
            _fake_definition("http_request"),
            _fake_definition("slack_notify", risk=RiskLevel.MEDIUM),
            _fake_definition("file_read", is_mvp=False),
        ]
    )
    app.dependency_overrides[get_node_definition_repository] = lambda: fake_repo
    _override_permission(app)

    client = TestClient(app)
    resp = client.get("/api/v1/nodes/catalog", headers={"Authorization": f"Bearer {_bearer_token()}"})

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 3
    types = {item["node_type"] for item in body}
    assert types == {"http_request", "slack_notify", "file_read"}
    fake_repo.list_all.assert_awaited_once_with(mvp_only=False)

    # NodeConfig 응답 — embedding 필드 누락 검증 (페이로드 부담 방지)
    assert all("embedding" not in item for item in body)

    app.dependency_overrides.clear()


def test_catalog_mvp_filter(app) -> None:
    fake_repo = MagicMock()
    fake_repo.list_all = AsyncMock(return_value=[_fake_definition("http_request")])
    app.dependency_overrides[get_node_definition_repository] = lambda: fake_repo
    _override_permission(app)

    client = TestClient(app)
    resp = client.get(
        "/api/v1/nodes/catalog?mvp_only=true",
        headers={"Authorization": f"Bearer {_bearer_token()}"},
    )

    assert resp.status_code == 200
    fake_repo.list_all.assert_awaited_once_with(mvp_only=True)
    app.dependency_overrides.clear()


def test_catalog_requires_bearer(app) -> None:
    """AuthMiddleware가 /nodes/catalog 차단 검증 — Bearer 없으면 401."""
    client = TestClient(app)
    resp = client.get("/api/v1/nodes/catalog")
    assert resp.status_code == 401


def test_catalog_risk_level_serialized(app) -> None:
    fake_repo = MagicMock()
    fake_repo.list_all = AsyncMock(
        return_value=[_fake_definition("admin_op", risk=RiskLevel.RESTRICTED)]
    )
    app.dependency_overrides[get_node_definition_repository] = lambda: fake_repo
    _override_permission(app)

    client = TestClient(app)
    resp = client.get("/api/v1/nodes/catalog", headers={"Authorization": f"Bearer {_bearer_token()}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["risk_level"] == "Restricted"
    app.dependency_overrides.clear()
