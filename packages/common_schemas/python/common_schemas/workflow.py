from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .enums import RiskLevel


class Position(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: float
    y: float


class Edge(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_instance_id: UUID
    to_instance_id: UUID
    from_handle: str
    to_handle: str


class NodeInstance(BaseModel):
    model_config = ConfigDict(frozen=True)

    instance_id: UUID
    node_id: UUID
    parameters: dict[str, Any]
    credential_id: Optional[UUID] = None
    position: Position


class NodeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: UUID
    node_type: str
    name: str
    category: str
    version: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    parameter_schema: dict[str, Any]
    risk_level: RiskLevel
    required_connections: list[str]
    description: str
    is_mvp: bool


class NodeExecutionState(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_instance_id: UUID
    status: Literal["pending", "running", "succeeded", "failed", "retrying", "cancelled"]
    attempt: int = 0
    last_error: Optional[str] = None


class WorkflowSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    workflow_id: UUID
    name: str
    description: Optional[str] = None
    scope: Literal["private", "team", "public"]
    is_draft: bool
    draft_spec: Optional[DraftSpec] = None
    nodes: list[NodeInstance]
    connections: list[Edge]
    version: Optional[int] = None
    sha256: Optional[str] = None
    created_via_session_id: Optional[UUID] = None

    def validate_graph(self) -> bool:
        node_ids = {n.instance_id for n in self.nodes}
        for edge in self.connections:
            if edge.from_instance_id not in node_ids:
                return False
            if edge.to_instance_id not in node_ids:
                return False
        return True


# Forward reference resolved after DraftSpec is defined in agent.py
# Call WorkflowSchema.model_rebuild() after importing DraftSpec
