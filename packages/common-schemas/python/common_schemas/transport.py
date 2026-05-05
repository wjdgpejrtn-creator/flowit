from __future__ import annotations

from typing import Annotated, Any, Literal, Union
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
    ],
    Discriminator(_get_frame_discriminator),
]
