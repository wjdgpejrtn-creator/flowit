"""POST /api/v1/skills/extract — 문서→스킬 추출 SSE 프록시 라우트 테스트 (REQ-010/013).

검증축:
- 가드: client 미설정(503) / 문서 미존재(404) / 타인 문서(403) / blocks 없음(409)
- happy path: skills-builder 봉투를 unwrap해 frame을 SSE로 재전송 (extract는 저장 X)
- 프록시 페이로드 계약: source_type="sop", step="extract", document 포함
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.dependencies.clients import get_skills_builder_http
from app.dependencies.permission import get_permission_source
from app.dependencies.repositories import get_document_repository
from app.routers.skills import router as skills_router
from common_schemas import PermissionSource
from fastapi import FastAPI
from fastapi.testclient import TestClient

_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_OTHER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_DOC_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _fake_permission() -> PermissionSource:
    return PermissionSource(
        user_id=_USER_ID,
        role="User",  # type: ignore[arg-type]
        department_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )


# ── skills-builder 응답을 흉내내는 가짜 httpx.AsyncClient ───────────────────────


class _FakeStreamCtx:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    async def __aenter__(self) -> _FakeStreamCtx:
        return self

    async def __aexit__(self, *_a) -> bool:
        return False

    async def aiter_lines(self):
        for ln in self._lines:
            yield ln


class _FakeSkillsBuilderClient:
    """`.stream(method, url, json=..., timeout=...)` → async ctx 로 SSE 라인 방출."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.captured: dict | None = None

    def stream(self, method: str, url: str, **kwargs):
        self.captured = {"method": method, "url": url, **kwargs}
        return _FakeStreamCtx(self._lines)


def _make_doc(*, user_id=_USER_ID, blocks=("blk",)):
    doc = MagicMock()
    doc.user_id = user_id
    doc.blocks = list(blocks)
    doc.model_dump.return_value = {"document_id": str(_DOC_ID), "blocks": ["..."]}
    return doc


def _make_app(*, client=..., doc=...) -> FastAPI:
    app = FastAPI()
    app.include_router(skills_router)
    app.dependency_overrides[get_permission_source] = _fake_permission

    # client=...(미지정) → 기본 가짜 client. None 지정 시 503 경로.
    resolved_client = _FakeSkillsBuilderClient([]) if client is ... else client
    app.dependency_overrides[get_skills_builder_http] = lambda: resolved_client

    doc_repo = MagicMock()
    resolved_doc = _make_doc() if doc is ... else doc
    doc_repo.get_by_id = AsyncMock(return_value=resolved_doc)
    app.dependency_overrides[get_document_repository] = lambda: doc_repo
    return app


def _post(app: FastAPI):
    with TestClient(app) as tc:
        return tc.post("/api/v1/skills/extract", json={"source_document_id": str(_DOC_ID)})


def test_extract_503_when_client_unconfigured():
    res = _post(_make_app(client=None))
    assert res.status_code == 503
    assert "SKILLS_BUILDER_URL" in res.json()["detail"]


def test_extract_404_when_document_missing():
    res = _post(_make_app(doc=None))
    assert res.status_code == 404


def test_extract_403_when_document_other_owner():
    res = _post(_make_app(doc=_make_doc(user_id=_OTHER_ID)))
    assert res.status_code == 403


def test_extract_409_when_no_blocks():
    res = _post(_make_app(doc=_make_doc(blocks=())))
    assert res.status_code == 409


def test_extract_streams_unwrapped_frames():
    result_frame = {
        "frame_type": "result",
        "intent": "build_skill",
        "payload": {
            "skills": [
                {
                    "node_type": "send_report",
                    "name": "주간 리포트 발송",
                    "description": "리포트를 슬랙으로 발송",
                    "instructions": "## When to use\n...",
                }
            ]
        },
    }
    envelope = {"frames": [result_frame], "next_action": "complete", "state_delta": {}}
    fake = _FakeSkillsBuilderClient([f"data: {json.dumps(envelope, ensure_ascii=False)}"])

    res = _post(_make_app(client=fake))
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    # 봉투가 unwrap되어 frame 자체가 data: 라인으로 재전송됐는지
    assert "build_skill" in res.text
    assert "주간 리포트 발송" in res.text
    # 프록시 계약 — sop/extract + document 포함
    assert fake.captured is not None
    assert fake.captured["url"] == "/v1/agent/route"
    sent = fake.captured["json"]
    assert sent["payload"]["source_type"] == "sop"
    assert sent["payload"]["step"] == "extract"
    assert "document" in sent["payload"]
