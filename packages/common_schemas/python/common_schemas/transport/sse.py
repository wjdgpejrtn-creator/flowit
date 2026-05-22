from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Discriminator, Tag


class SSEFrame(BaseModel):
    model_config = ConfigDict(frozen=True)

    frame_type: str


class SessionFrame(SSEFrame):
    frame_type: Literal["session"] = "session"
    session_id: UUID
    langgraph_thread_id: UUID


class AgentNodeFrame(SSEFrame):
    frame_type: Literal["agent_node"] = "agent_node"
    agent_node_name: str


class RationaleDeltaFrame(SSEFrame):
    frame_type: Literal["rationale_delta"] = "rationale_delta"
    delta: str


class SlotFillQuestionFrame(SSEFrame):
    frame_type: Literal["slot_fill_question"] = "slot_fill_question"
    question: str
    field_name: str


class DraftSpecDeltaFrame(SSEFrame):
    frame_type: Literal["draft_spec_delta"] = "draft_spec_delta"
    delta: dict[str, Any]


class ResultFrame(SSEFrame):
    frame_type: Literal["result"] = "result"
    intent: str
    payload: dict[str, Any]


class ErrorFrame(SSEFrame):
    frame_type: Literal["error"] = "error"
    code: str
    message: str


# --- 실시간 모니터링 프레임 (오른쪽 사이드바) ---

class PipelineStatusFrame(SSEFrame):
    """생성 파이프라인 각 서비스의 진행 상태. 오른쪽 사이드바 실시간 표시용."""
    frame_type: Literal["pipeline_status"] = "pipeline_status"
    service_name: str
    status: Literal["started", "completed", "failed"]
    elapsed_ms: Optional[int] = None


class IntentResultFrame(SSEFrame):
    """의도 분석 결과 — 인텐트 분류 + 추출 엔티티. 오른쪽 사이드바 표시용."""
    frame_type: Literal["intent_result"] = "intent_result"
    intent: str
    entities: dict[str, Any]


class QAMetricFrame(SSEFrame):
    """QA 평가 결과 — 점수 + 시도 횟수 + 통과 여부. 오른쪽 사이드바 표시용."""
    frame_type: Literal["qa_metric"] = "qa_metric"
    score: float
    attempt: int
    pass_flag: bool
    feedback: str


class WorkflowDraftFrame(SSEFrame):
    """워크플로우 초안 — 노드 목록 + 연결 구조. 가운데 캔버스 실시간 시각화용."""
    frame_type: Literal["workflow_draft"] = "workflow_draft"
    nodes: list[dict[str, Any]]
    connections: list[dict[str, Any]]


class ChatMessageFrame(SSEFrame):
    """대화 메시지 본문 — 유저 입력 / AI assistant 응답.

    파이프라인 상태 프레임만으로는 모니터링에서 대화 내용을 재생할 수 없어,
    SessionFrameStore가 유저 메시지·assistant 응답을 함께 기록하도록 추가된 프레임.
    """
    frame_type: Literal["chat_message"] = "chat_message"
    role: Literal["user", "assistant"]
    content: str


def _get_frame_discriminator(v: Any) -> str:
    if isinstance(v, dict):
        return v.get("frame_type", "")
    return getattr(v, "frame_type", "")


AnySSEFrame = Annotated[
    Union[
        Annotated[SessionFrame, Tag("session")],
        Annotated[AgentNodeFrame, Tag("agent_node")],
        Annotated[RationaleDeltaFrame, Tag("rationale_delta")],
        Annotated[SlotFillQuestionFrame, Tag("slot_fill_question")],
        Annotated[DraftSpecDeltaFrame, Tag("draft_spec_delta")],
        Annotated[ResultFrame, Tag("result")],
        Annotated[ErrorFrame, Tag("error")],
        Annotated[PipelineStatusFrame, Tag("pipeline_status")],
        Annotated[IntentResultFrame, Tag("intent_result")],
        Annotated[QAMetricFrame, Tag("qa_metric")],
        Annotated[WorkflowDraftFrame, Tag("workflow_draft")],
        Annotated[ChatMessageFrame, Tag("chat_message")],
    ],
    Discriminator(_get_frame_discriminator),
]
