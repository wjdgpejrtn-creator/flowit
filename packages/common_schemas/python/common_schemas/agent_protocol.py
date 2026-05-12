"""Inter-agent HTTP 통신 계약 (Sprint 3 §2.4).

orchestrator Modal app ↔ sub-agent Modal app(composer/skills_builder/personalization)
간 단일 프로토콜. 모든 sub-agent는 `POST /v1/agent/route`로 동일 요청·응답 스키마를
받는다. VPC 내부 통신 한정 (옵션 C).
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .agent import AgentState, MemoryEntry
from .transport import AnySSEFrame


class AgentProtocolRequest(BaseModel):
    """Orchestrator → sub-agent 요청 페이로드.

    payload는 sub-agent별 추가 입력(예: Skills Builder의 ``document``,
    Personalization의 ``query``)을 담는 자유 dict. 각 sub-agent는 자체 어댑터
    레이어에서 payload를 검증한다.
    """

    model_config = ConfigDict(frozen=True)

    session_id: UUID
    user_id: UUID
    state: AgentState
    personal_memory: list[MemoryEntry] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None


class AgentProtocolResponse(BaseModel):
    """Sub-agent → orchestrator SSE 응답 청크.

    하나의 응답은 SSE 스트림 한 chunk를 의미한다. 스트림 전체가 끝나기 전까지는
    next_action="continue"로 유지하고, 정상 완료 시 "complete", 오류 시 "error".
    state_delta는 orchestrator가 다음 hop의 AgentState에 merge할 부분 갱신.
    """

    model_config = ConfigDict(frozen=True)

    frames: list[AnySSEFrame] = Field(default_factory=list)
    state_delta: dict[str, Any] = Field(default_factory=dict)
    next_action: Literal["continue", "complete", "error"]
