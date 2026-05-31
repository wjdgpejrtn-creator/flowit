"""SSE 응답 헤더 회귀 테스트.

Google Cloud LB가 text/event-stream 응답에 Content-Encoding: gzip을 적용해
브라우저가 frame을 수신 못 하는 사고 재발 방지. 두 SSE endpoint(create_session,
stream_session_frames)에 no-transform / X-Accel-Buffering / keep-alive 헤더가
들어가는지 검증.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies.clients import get_orchestrator_http
from app.dependencies.permission import get_permission_source
from app.main import create_app
from common_schemas import PermissionSource


@pytest.fixture
def app(env_minimum: None):
    return create_app(Settings())  # type: ignore[call-arg]


def _override_permission(app) -> None:
    fake = PermissionSource(
        user_id=uuid4(),
        role="User",  # type: ignore[arg-type]
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )
    app.dependency_overrides[get_permission_source] = lambda: fake


def _override_orchestrator(app, *, body: bytes = b"data: {\"frames\": []}\n\n") -> None:
    """httpx.AsyncClient의 stream + get을 mock."""

    def handler(request: httpx.Request) -> httpx.Response:
        # path에 따라 stream(POST /v1/agent/route) 또는 GET frames 모두 동일 본문
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    mock_transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://mock", transport=mock_transport)
    app.dependency_overrides[get_orchestrator_http] = lambda: client


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


_EXPECTED_HEADERS = {
    "cache-control": "no-cache, no-transform",
    "x-accel-buffering": "no",
    "connection": "keep-alive",
}


def _assert_sse_headers(headers) -> None:
    for k, v in _EXPECTED_HEADERS.items():
        assert headers.get(k) is not None, f"missing SSE header: {k}"
        assert v in headers[k].lower(), f"{k} expected to contain {v!r}, got {headers[k]!r}"
    assert "text/event-stream" in headers.get("content-type", ""), headers.get("content-type")


def test_create_session_sse_headers_present(app):
    """POST /api/v1/agents/sessions — no-transform 헤더가 응답에 포함되는지 검증."""
    _override_permission(app)
    _override_orchestrator(app)
    client = TestClient(app)
    with client.stream(
            "POST",
            "/api/v1/agents/sessions",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {_bearer_token()}"},
        ) as resp:
            assert resp.status_code == 200
            _assert_sse_headers(resp.headers)
            # body 소비해서 generator close
            list(resp.iter_lines())


def test_stream_session_frames_sse_headers_present(app):
    """GET /api/v1/ai/sessions/{id}/stream — no-transform 헤더가 응답에 포함되는지 검증."""
    _override_permission(app)
    _override_orchestrator(app, body=b'{"frames": []}')
    client = TestClient(app)
    with client.stream(
            "GET",
            f"/api/v1/ai/sessions/{uuid4()}/stream",
            headers={"Authorization": f"Bearer {_bearer_token()}"},
        ) as resp:
            assert resp.status_code == 200
            _assert_sse_headers(resp.headers)
            list(resp.iter_lines())


def test_slot_answer_streams_round2_payload_to_orchestrator(app):
    """POST /sessions/{id}/slot — 스킬 선택을 round=2 + selected_skill_id로 orchestrator에 프록시(REQ-013)."""
    _override_permission(app)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured.update(_json.loads(request.content))
        return httpx.Response(
            200,
            content=b'data: {"frames": []}\n\n',
            headers={"content-type": "text/event-stream"},
        )

    mock_transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(base_url="http://mock", transport=mock_transport)
    app.dependency_overrides[get_orchestrator_http] = lambda: mock_client

    skill_id = str(uuid4())
    client = TestClient(app)
    with client.stream(
        "POST",
        f"/api/v1/agents/sessions/{uuid4()}/slot",
        json={"skill_id": skill_id, "field_name": "skill_selection"},
        headers={"Authorization": f"Bearer {_bearer_token()}"},
    ) as resp:
        assert resp.status_code == 200
        _assert_sse_headers(resp.headers)
        list(resp.iter_lines())

    assert captured["payload"]["round"] == 2
    assert captured["payload"]["selected_skill_id"] == skill_id
