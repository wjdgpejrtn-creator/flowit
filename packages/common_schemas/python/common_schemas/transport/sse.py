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


class SkillOption(BaseModel):
    """스킬 선택지 1개 — SkillSelectionFrame.options 원소 (REQ-013 two-shot HITL)."""
    model_config = ConfigDict(frozen=True)

    skill_id: UUID
    name: str
    description: str
    document_preview: Optional[str] = None    # SkillDocument.instructions 앞부분(선택)
    node_definition_id: Optional[UUID] = None  # 노드형 스킬 호환(지침서형은 None)
    is_personal: bool = False                  # 본인 소유 개인 스킬 — 프론트 "⭐ 자주 사용" 배지 (REQ-013 개인화 추천)


class SkillSelectionFrame(SSEFrame):
    """스킬 검색 후 사용자에게 적용할 스킬을 옵션으로 제시(two-shot HITL 1차).

    프론트가 옵션을 렌더 → 사용자 선택 → `POST /sessions/{id}/slot`
    (`field_name`, `skill_id`)로 2차 라운드 트리거. SlotFillQuestionFrame과 달리
    복수 옵션 + skill_id + 미리보기를 담는다.
    """
    frame_type: Literal["skill_selection"] = "skill_selection"
    field_name: str = "skill_selection"
    prompt: str
    options: list[SkillOption]
    allow_skip: bool = True


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


class SkillBuilderWizardFrame(SSEFrame):
    """스킬 빌드 위저드 트리거 — ``build_skill`` 의도 분류 시 supervisor가 발행한다(REQ-010).

    프론트는 이 프레임을 받으면 AI 채팅의 우측 캔버스를 '스킬 상세 편집'으로 전환하고
    좌측 대화에 위저드 '재료 선택' 카드를 인라인으로 띄운다. 위저드의 실제 빌드(추출·
    생성·게시)는 프론트 REST(skillApi)가 자가구동하므로, 이 프레임은 '위저드를 띄워라'는
    신호 + (있으면) 문서 컨텍스트만 싣는다. 단일 build_skill에서만 발행되고, 복합
    ``skill_then_compose``는 기존 서브에이전트 relay를 유지한다(composer가 selected_skill_id 소비).
    """
    frame_type: Literal["skill_builder_wizard"] = "skill_builder_wizard"
    source_document_id: Optional[UUID] = None


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
        Annotated[SkillSelectionFrame, Tag("skill_selection")],
        Annotated[DraftSpecDeltaFrame, Tag("draft_spec_delta")],
        Annotated[ResultFrame, Tag("result")],
        Annotated[ErrorFrame, Tag("error")],
        Annotated[PipelineStatusFrame, Tag("pipeline_status")],
        Annotated[IntentResultFrame, Tag("intent_result")],
        Annotated[QAMetricFrame, Tag("qa_metric")],
        Annotated[WorkflowDraftFrame, Tag("workflow_draft")],
        Annotated[ChatMessageFrame, Tag("chat_message")],
        Annotated[SkillBuilderWizardFrame, Tag("skill_builder_wizard")],
    ],
    Discriminator(_get_frame_discriminator),
]
