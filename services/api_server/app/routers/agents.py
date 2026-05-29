from __future__ import annotations

import json
import logging
from uuid import uuid4

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dependencies.clients import get_orchestrator_http
from app.dependencies.permission import get_permission_source
from common_schemas import PermissionSource

logger = logging.getLogger(__name__)

# 두 prefix 분리 — /api/v1/agents/* 와 /api/v1/ai/sessions/* 가 다른 path 구조라
# 단일 prefix로 묶으면 라우터 컨벤션이 깨지므로 APIRouter를 분리.
agents_router = APIRouter(prefix="/api/v1/agents", tags=["agents"])
ai_sessions_router = APIRouter(prefix="/api/v1/ai/sessions", tags=["agents"])

# AgentProtocolResponse(frames, state_delta, next_action)는 common_schemas.agent_protocol에 정의.
# 여기서는 raw dict으로 다루는 프록시라 import 없이 envelope.get("frames") 로만 접근.
_PROXY_TIMEOUT = 290.0  # Cloud Run 기본 request timeout 300s 이내로 보수적으로 설정

# SSE 응답 표준 헤더 — Google Cloud LB의 gzip 압축으로 SSE 스트리밍이 깨지는 것 차단.
# - Cache-Control no-transform: LB에 응답 바디 변환 금지 지시 (핵심)
# - X-Accel-Buffering no: nginx/reverse-proxy 버퍼링 차단
# - Connection keep-alive: HTTP/1.1 keep-alive 명시
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


class SessionRequest(BaseModel):
    message: str
    session_id: str | None = None


def _orchestrator_or_503(client: httpx.AsyncClient | None) -> httpx.AsyncClient:
    if client is None:
        raise HTTPException(status_code=503, detail="Orchestrator unavailable — ORCHESTRATOR_URL 미설정")
    return client


def _build_agent_payload(session_id: str, user_id: str, message: str) -> dict:
    return {
        "session_id": session_id,
        "user_id": user_id,
        "personal_memory": [],
        "payload": {"message": message},
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


def _unwrap_sse(raw: str):
    """AgentProtocolResponse(common_schemas.agent_protocol) 봉투에서 frame을 꺼내 SSE 라인으로 변환."""
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return
    for frame in envelope.get("frames", []):
        yield f"data: {json.dumps(frame, ensure_ascii=False)}\n\n"


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
                    for frame_line in _unwrap_sse(line[6:]):
                        yield frame_line
        except Exception as exc:
            logger.error("agent-composer 스트리밍 실패: %s", exc)
            err = {"frame_type": "error", "code": "E_PROXY", "message": str(exc)}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@agents_router.post("/sessions/{session_id}/slot", status_code=204)
async def send_slot_answer(
    session_id: str,
    body: dict = Body(...),
    permission: PermissionSource = Depends(get_permission_source),
) -> None:
    """슬롯 필링 답변 수신 — TODO: agent-composer 슬롯 API 연동 후속 PR에서 처리."""
    logger.info("slot answer received for session %s: %s", session_id, body)


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

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)
