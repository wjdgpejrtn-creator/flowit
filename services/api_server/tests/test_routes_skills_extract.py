"""POST /api/v1/skills/extract + extract/detail + GET /skills/templates — 위저드 추출 경로 테스트 (REQ-010/013).

옵션 1(2단계 분리) — LLM JSON 잘림 해소:
- POST /extract: 메타 5필드 SSE 스트림 (저장 X, 카드 그리드용)
- POST /extract/detail: 선택된 메타에 대한 detail JSON 응답 (저장 X, 폼 prefill용)

검증축:
- 가드: client 미설정(503) / 문서 미존재(404) / 타인 문서(403) / blocks 없음(409)
- happy path(문서): skills-builder 봉투를 unwrap해 frame을 SSE로 재전송 (extract는 저장 X)
- 프록시 페이로드 계약: source_type="sop", step ∈ {"metadata", "detail"}, document/meta 포함
- default 템플릿: GET /templates 메타 노출 + template_code 추출(seed→SOP 합성, doc_repo 미사용)
- 재료 배타: source_document_id XOR template_code (둘 다/둘 다 없음 → 422)
- detail 응답: ResultFrame 수집 후 JSON, ErrorFrame이면 422, 응답 없음이면 502
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


def _make_chunk(content: str):
    chunk = MagicMock()
    chunk.model_dump.return_value = {"chunk_index": 0, "block": {"content": content}}
    return chunk


def _make_app(*, client=..., doc=..., chunks=()) -> FastAPI:
    app = FastAPI()
    app.include_router(skills_router)
    app.dependency_overrides[get_permission_source] = _fake_permission

    # client=...(미지정) → 기본 가짜 client. None 지정 시 503 경로.
    resolved_client = _FakeSkillsBuilderClient([]) if client is ... else client
    app.dependency_overrides[get_skills_builder_http] = lambda: resolved_client

    doc_repo = MagicMock()
    resolved_doc = _make_doc() if doc is ... else doc
    doc_repo.get_by_id = AsyncMock(return_value=resolved_doc)
    # 옵션 C — extract/detail이 문서 경로에서 청크를 로드해 payload에 싣는다(map-reduce/RAG).
    doc_repo.get_chunks = AsyncMock(return_value=list(chunks))
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
            "skill_metas": [
                {
                    "node_type": "send_report",
                    "name": "주간 리포트 발송",
                    "description": "리포트를 슬랙으로 발송",
                    "category": "action",
                    "risk_level": "Low",
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
    # 프록시 계약 — sop/metadata + document 포함
    assert fake.captured is not None
    assert fake.captured["url"] == "/v1/agent/route"
    sent = fake.captured["json"]
    assert sent["payload"]["source_type"] == "sop"
    assert sent["payload"]["step"] == "metadata"
    assert "document" in sent["payload"]


def test_extract_includes_chunks_in_proxy_payload():
    # 옵션 C: 문서 경로에서 document_chunks를 로드해 payload.chunks로 실어 보낸다(8192 초과 회귀 차단).
    fake = _FakeSkillsBuilderClient([])
    res = _post(_make_app(client=fake, chunks=[_make_chunk("Slack 알림 절차"), _make_chunk("에스컬레이션")]))
    assert res.status_code == 200
    sent = fake.captured["json"]
    assert len(sent["payload"]["chunks"]) == 2
    assert sent["payload"]["chunks"][0]["block"]["content"] == "Slack 알림 절차"


def test_extract_template_path_sends_empty_chunks():
    # 합성 템플릿(ecommerce seed)은 청크가 없으므로 빈 리스트 — use case가 전체 문서 폴백.
    fake = _FakeSkillsBuilderClient([f"data: {json.dumps({'frames': []})}"])
    app = _make_app(client=fake)
    with TestClient(app) as tc:
        res = tc.post("/api/v1/skills/extract", json={"template_code": "ecommerce"})
    assert res.status_code == 200
    assert fake.captured["json"]["payload"]["chunks"] == []


# ── GET /templates + default(template_code) 추출 경로 ─────────────────────────


def test_list_templates_returns_industry_and_functional():
    app = _make_app()
    with TestClient(app) as tc:
        res = tc.get("/api/v1/skills/templates")
    assert res.status_code == 200
    body = res.json()
    codes = {t["code"] for t in body}
    kinds = {t["kind"] for t in body}
    # seed 11종(산업 6 + 직무 5) — 대표 코드 + 두 kind 노출 확인
    assert "ecommerce" in codes
    assert "marketing" in codes
    assert kinds == {"industry", "functional"}
    for t in body:
        assert t["code"] and t["name"] and t["kind"] in {"industry", "functional"}


def test_extract_with_template_code_synthesizes_and_proxies():
    """template_code → seed를 SOP 문서로 합성 후 sop/metadata 프록시. doc_repo는 호출되지 않는다."""
    envelope = {"frames": [], "next_action": "complete", "state_delta": {}}
    fake = _FakeSkillsBuilderClient([f"data: {json.dumps(envelope)}"])
    app = _make_app(client=fake)
    with TestClient(app) as tc:
        res = tc.post("/api/v1/skills/extract", json={"template_code": "ecommerce"})
    assert res.status_code == 200
    sent = fake.captured["json"]
    assert sent["payload"]["source_type"] == "sop"
    assert sent["payload"]["step"] == "metadata"
    # 합성된 DocumentBlock에 SOP 본문 블록이 실려야(문서 경로와 동일 계약)
    assert sent["payload"]["document"]["blocks"]


def test_extract_with_unknown_template_code_404():
    fake = _FakeSkillsBuilderClient([])
    app = _make_app(client=fake)
    with TestClient(app) as tc:
        res = tc.post("/api/v1/skills/extract", json={"template_code": "does-not-exist"})
    assert res.status_code == 404


def test_extract_requires_exactly_one_source():
    app = _make_app()
    with TestClient(app) as tc:
        # 둘 다 없음 → 422
        assert tc.post("/api/v1/skills/extract", json={}).status_code == 422
        # 둘 다 있음 → 422
        both = {"source_document_id": str(_DOC_ID), "template_code": "ecommerce"}
        assert tc.post("/api/v1/skills/extract", json=both).status_code == 422


# ── POST /extract/detail — 옵션 1 2차 호출 (JSON 응답) ──────────────────────────


def _meta_dict() -> dict:
    return {
        "node_type": "send_report",
        "name": "주간 리포트 발송",
        "description": "리포트를 슬랙으로 발송",
        "category": "action",
        "risk_level": "Low",
    }


def _post_detail(app: FastAPI, *, source: dict | None = None, meta: dict | None = None):
    body: dict = source if source is not None else {"source_document_id": str(_DOC_ID)}
    body["meta"] = meta if meta is not None else _meta_dict()
    with TestClient(app) as tc:
        return tc.post("/api/v1/skills/extract/detail", json=body)


def _detail_result_envelope(skill_detail: dict) -> str:
    """skills-builder의 ResultFrame 봉투 SSE 라인 1개 생성."""
    frame = {
        "frame_type": "result",
        "intent": "build_skill",
        "payload": {"skill_detail": skill_detail},
    }
    envelope = {"frames": [frame], "next_action": "complete", "state_delta": {}}
    return f"data: {json.dumps(envelope, ensure_ascii=False)}"


def _detail_sample() -> dict:
    return {
        "node_type": "send_report",
        "instructions": "## When to use\n주간 리포트 발송 시.\n## Steps\n...",
        "inputs": {"type": "object", "properties": {"channel": {"type": "string"}}},
        "outputs": {"type": "object", "properties": {"ts": {"type": "string"}}},
        "required_connections": ["slack"],
        "service_type": "slack",
        "staging": {
            "category": "action", "input_schema": {}, "output_schema": {},
            "risk_level": "Low", "required_connections": ["slack"], "service_type": "slack",
        },
    }


def test_extract_detail_503_when_client_unconfigured():
    res = _post_detail(_make_app(client=None))
    assert res.status_code == 503


def test_extract_detail_404_when_document_missing():
    res = _post_detail(_make_app(doc=None))
    assert res.status_code == 404


def test_extract_detail_403_when_other_owner():
    res = _post_detail(_make_app(doc=_make_doc(user_id=_OTHER_ID)))
    assert res.status_code == 403


def test_extract_detail_409_when_no_blocks():
    res = _post_detail(_make_app(doc=_make_doc(blocks=())))
    assert res.status_code == 409


def test_extract_detail_unknown_template_404():
    fake = _FakeSkillsBuilderClient([])
    app = _make_app(client=fake)
    res = _post_detail(app, source={"template_code": "does-not-exist"})
    assert res.status_code == 404


def test_extract_detail_returns_json_skill_detail():
    fake = _FakeSkillsBuilderClient([_detail_result_envelope(_detail_sample())])
    res = _post_detail(_make_app(client=fake))
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    body = res.json()
    assert body["skill_detail"]["node_type"] == "send_report"
    assert body["skill_detail"]["instructions"].startswith("## When to use")
    assert body["skill_detail"]["staging"]["category"] == "action"


def test_extract_detail_proxy_contract_includes_meta_and_step():
    """프록시 페이로드 — step="detail" + meta가 그대로 전달, document 포함."""
    fake = _FakeSkillsBuilderClient([_detail_result_envelope(_detail_sample())])
    res = _post_detail(_make_app(client=fake))
    assert res.status_code == 200
    sent = fake.captured["json"]
    assert sent["payload"]["source_type"] == "sop"
    assert sent["payload"]["step"] == "detail"
    assert sent["payload"]["meta"] == _meta_dict()
    assert "document" in sent["payload"]


def test_extract_detail_with_template_code():
    """template_code 경로 — seed → SOP 합성 후 detail 호출."""
    fake = _FakeSkillsBuilderClient([_detail_result_envelope(_detail_sample())])
    app = _make_app(client=fake)
    res = _post_detail(app, source={"template_code": "ecommerce"})
    assert res.status_code == 200
    sent = fake.captured["json"]
    assert sent["payload"]["step"] == "detail"
    assert sent["payload"]["document"]["blocks"]


def test_extract_detail_upstream_llm_failure_yields_502():
    """상류 LLM 실패(E_LLM_GENERATION_FAILED/E_LLM_RESPONSE_INVALID) → 502 (조장 리뷰 LOW #3)."""
    error_frame = {"frame_type": "error", "code": "E_LLM_GENERATION_FAILED", "message": "modal timeout"}
    envelope = {"frames": [error_frame], "next_action": "error", "state_delta": {}}
    fake = _FakeSkillsBuilderClient([f"data: {json.dumps(envelope)}"])
    res = _post_detail(_make_app(client=fake))
    assert res.status_code == 502
    body = res.json()
    assert body["detail"]["code"] == "E_LLM_GENERATION_FAILED"


def test_extract_detail_client_validation_failure_yields_422():
    """클라이언트/메타 검증 실패(E_META_INVALID/E_DOCUMENT_EMPTY 등) → 422."""
    error_frame = {"frame_type": "error", "code": "E_META_INVALID", "message": "메타 검증 실패"}
    envelope = {"frames": [error_frame], "next_action": "error", "state_delta": {}}
    fake = _FakeSkillsBuilderClient([f"data: {json.dumps(envelope)}"])
    res = _post_detail(_make_app(client=fake))
    assert res.status_code == 422
    body = res.json()
    assert body["detail"]["code"] == "E_META_INVALID"


def test_extract_detail_no_result_yields_502():
    """ResultFrame이 없으면 502 (upstream 응답 비정상)."""
    envelope = {"frames": [], "next_action": "complete", "state_delta": {}}
    fake = _FakeSkillsBuilderClient([f"data: {json.dumps(envelope)}"])
    res = _post_detail(_make_app(client=fake))
    assert res.status_code == 502


def test_extract_detail_missing_meta_field_422():
    """meta에 필수 필드 누락 시 Pydantic validator가 422."""
    bad_meta = {"node_type": "x", "name": "y", "description": "z", "category": "action"}  # risk_level 누락
    res = _post_detail(_make_app(), meta=bad_meta)
    assert res.status_code == 422


def test_extract_detail_requires_exactly_one_source():
    app = _make_app()
    with TestClient(app) as tc:
        # 둘 다 없음
        assert tc.post("/api/v1/skills/extract/detail", json={"meta": _meta_dict()}).status_code == 422
        # 둘 다 있음
        both = {
            "source_document_id": str(_DOC_ID),
            "template_code": "ecommerce",
            "meta": _meta_dict(),
        }
        assert tc.post("/api/v1/skills/extract/detail", json=both).status_code == 422
