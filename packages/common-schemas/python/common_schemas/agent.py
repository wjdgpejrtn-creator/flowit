from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .enums import AgentMode, ExecutionStatus
from .workflow import NodeConfig, WorkflowSchema


class UnresolvedNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    placeholder_id: str
    hint: str
    candidate_node_types: list[str]


class SlotFillingState(BaseModel):
    model_config = ConfigDict(frozen=True)

    asked: list[str]
    pending: list[str]
    filled: dict[str, Any]


class DraftSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    natural_language_intent: str
    unresolved_nodes: list[UnresolvedNode]
    discovered_entities: dict[str, Any]
    slot_filling_state: SlotFillingState
    consultant_turn_count: int


class IntentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: Literal["clarify", "draft", "refine", "propose"]
    confidence: float
    analyzed_entities: dict[str, Any]


class AgentState(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: UUID
    user_id: UUID
    messages: list[Any]
    turn_count: int = Field(le=25)
    mode: AgentMode
    draft_spec: Optional[DraftSpec] = None
    intent_result: Optional[IntentResult] = None
    node_candidates: list[NodeConfig] = Field(default_factory=list)
    workflow_draft: Optional[WorkflowSchema] = None
    execution_status: ExecutionStatus


WorkflowSchema.model_rebuild()
