from __future__ import annotations

import json
import logging
from uuid import uuid4

import httpx
from common_schemas import PermissionSource
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dependencies.clients import get_orchestrator_http
from app.dependencies.permission import get_permission_source
from app.sse_proxy import SSE_HEADERS, unwrap_agent_sse

logger = logging.getLogger(__name__)

# 두 prefix 분리 — /api/v1/agents/* 와 /api/v1/ai/sessions/* 가 다른 path 구조라
# 단일 prefix로 묶으면 라우터 컨벤션이 깨지므로 APIRouter를 분리.
agents_router = APIRouter(prefix="/api/v1/agents", tags=["agents"])
ai_sessions_router = APIRouter(prefix="/api/v1/ai/sessions", tags=["agents"])

# AgentProtocolResponse(frames, state_delta, next_action)는 common_schemas.agent_protocol에 정의.
# 여기서는 raw dict으로 다루는 프록시라 import 없이 envelope.get("frames") 로만 접근.
_PROXY_TIMEOUT = 290.0  # Cloud Run 기본 request timeout 300s 이내로 보수적으로 설정

# SSE 표준 헤더(SSE_HEADERS) + 봉투 언래핑(unwrap_agent_sse)은 app.sse_proxy에 단일 정의 —
# skills 추출 라우터와 공유 (Google LB gzip 차단 헤더 SSOT).


class SessionRequest(BaseModel):
    message: str
    session_id: str | None = None


def _orchestrator_or_503(client: httpx.AsyncClient | None) -> httpx.AsyncClient:
    if client is None:
        raise HTTPException(status_code=503, detail="Orchestrator unavailable — ORCHESTRATOR_URL 미설정")
    return client


def _build_agent_payload(
    session_id: str,
    user_id: str,
    message: str,
    round: int = 1,
    selected_skill_id: str | None = None,
    field_name: str | None = None,
) -> dict:
    payload: dict = {"message": message, "round": round}
    if selected_skill_id:
        payload["selected_skill_id"] = selected_skill_id
    if field_name:
        payload["field_name"] = field_name
    return {
        "session_id": session_id,
        "user_id": user_id,
        "personal_memory": [],
        "payload": payload,
        "state": {
            "session_id": session_id,
            "user_id": user_id,
            "messages": [],
            "turn_count": 0,
            "mode": "general",
            "execution_status": "pending",
            "node_candidates": [],
        },
    }


@agents_router.post("/sessions")
async def create_session(
    req: SessionRequest = Body(...),
    permission: PermissionSource = Depends(get_permission_source),
    client: httpx.AsyncClient | None = Depends(get_orchestrator_http),
) -> StreamingResponse:
    """채팅 메시지를 agent-composer로 전달하고 SSE 스트림을 프록시한다.

    첫 번째 frame(frame_type='session')에 session_id와 langgraph_thread_id가 포함되어 있다.
    """
    orchestrator = _orchestrator_or_503(client)
    session_id = req.session_id or str(uuid4())
    user_id = str(permission.user_id)
    payload = _build_agent_payload(session_id, user_id, req.message)

    async def generate():
        try:
            async with orchestrator.stream(
                "POST", "/v1/agent/route", json=payload, timeout=_PROXY_TIMEOUT
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    for frame_line in unwrap_agent_sse(line[6:]):
                        yield frame_line
        except Exception as exc:
            logger.error("agent-composer 스트리밍 실패: %s", exc)
            err = {"frame_type": "error", "code": "E_PROXY", "message": str(exc)}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


@agents_router.post("/sessions/{session_id}/slot")
async def send_slot_answer(
    session_id: str,
    body: dict = Body(...),
    permission: PermissionSource = Depends(get_permission_source),
    client: httpx.AsyncClient | None = Depends(get_orchestrator_http),
) -> StreamingResponse:
    """스킬 선택(two-shot 2차) 답변을 받아 orchestrator로 round=2 스트림을 트리거한다 (REQ-013).

    1차 `SkillSelectionFrame`을 받은 프론트가 옵션 선택 후 `{skill_id, field_name}`로 호출.
    동일 session_id로 GCS 영속 상태를 복원해 draft→bind_skill→…을 이어 SSE로 프록시한다.
    `skill_id` 미지정(건너뛰기)이면 selected_skill_id=None으로 진행(바인딩 no-op).
    """
    orchestrator = _orchestrator_or_503(client)
    user_id = str(permission.user_id)
    selected_skill_id = body.get("skill_id") or body.get("selected_skill_id")
    field_name = body.get("field_name", "skill_selection")
    payload = _build_agent_payload(
        session_id, user_id, message="",
        round=2, selected_skill_id=selected_skill_id, field_name=field_name,
    )

    async def generate():
        try:
            async with orchestrator.stream(
                "POST", "/v1/agent/route", json=payload, timeout=_PROXY_TIMEOUT
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    for frame_line in unwrap_agent_sse(line[6:]):
                        yield frame_line
        except Exception as exc:
            logger.error("slot 답변 스트리밍 실패: %s", exc)
            err = {"frame_type": "error", "code": "E_PROXY", "message": str(exc)}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


@ai_sessions_router.get("/{session_id}/stream")
async def stream_session_frames(
    session_id: str,
    permission: PermissionSource = Depends(get_permission_source),
    client: httpx.AsyncClient | None = Depends(get_orchestrator_http),
) -> StreamingResponse:
    """저장된 세션 프레임을 SSE로 재전송 — 페이지 새로고침·재연결 복원용."""
    orchestrator = _orchestrator_or_503(client)
    user_id = str(permission.user_id)

    async def generate():
        try:
            resp = await orchestrator.get(
                f"/v1/agent/sessions/{session_id}/frames",
                params={"user_id": user_id},
            )
            if resp.status_code != 200:
                err = {"frame_type": "error", "code": "E_FRAMES", "message": "frames unavailable"}
                yield f"data: {json.dumps(err)}\n\n"
                return
            for frame in resp.json().get("frames", []):
                yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.error("세션 프레임 조회 실패: %s", exc)
            err = {"frame_type": "error", "code": "E_FRAMES", "message": str(exc)}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
