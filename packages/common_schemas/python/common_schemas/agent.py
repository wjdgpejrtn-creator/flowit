from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import AgentMode, ExecutionStatus
from .types import UtcDatetime
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

    intent: Literal["clarify", "draft", "refine", "propose", "build_skill"]
    confidence: float
    analyzed_entities: dict[str, Any]


MemoryType = Literal["preference", "correction", "workflow_pattern", "summary"]


class MemoryEntry(BaseModel):
    """에이전트 대화 메모리 항목 (Orchestrator ↔ sub-agent 전달용 payload + RDB SSOT).

    REQ-004 spec §1·§2.1 — protocol payload form. ai_agent 모듈은 본 클래스를
    re-export하며, RDB 저장 시에도 동일 스키마를 사용한다 (SSOT).
    """

    model_config = ConfigDict(frozen=True)

    entry_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    memory_type: MemoryType
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_session_id: Optional[UUID] = None
    created_at: UtcDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_ephemeral(self) -> bool:
        return not self.content.strip()


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
    personal_memory: list[MemoryEntry] = Field(default_factory=list)


WorkflowSchema.model_rebuild()
