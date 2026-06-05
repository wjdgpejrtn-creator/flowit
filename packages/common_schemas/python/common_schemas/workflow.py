from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
    # legacy 단일 바인딩 — provider 미지정(node 정의의 required_connections로 provider 추론).
    # 멀티커넥션 노드는 credential_ids를 사용한다.
    credential_id: Optional[UUID] = None
    # provider(service)별 credential 바인딩 — 멀티커넥션 노드(예: ["slack","google"]) 지원.
    # key는 required_connections의 provider 문자열. (REQ-012 credential 복수화)
    credential_ids: dict[str, UUID] = Field(default_factory=dict)
    # 바인딩된 SkillDocument(도메인 지침서) — 실행 시 LLM 노드 system 프롬프트에 주입 (REQ-013)
    skill_id: Optional[UUID] = None
    position: Position

    def resolve_credentials(self, required_connections: list[str]) -> dict[str, UUID]:
        """required provider별로 바인딩된 credential_id 매핑을 반환.

        ``credential_ids``(명시적 provider 바인딩)를 우선하고, required가 단일 provider이며
        legacy ``credential_id``만 있는 경우 그 provider에 매핑한다(하위호환). required에
        없는 provider 키는 제외한다.
        """
        resolved = {
            svc: cid for svc, cid in self.credential_ids.items() if svc in required_connections
        }
        if self.credential_id is not None and len(required_connections) == 1:
            resolved.setdefault(required_connections[0], self.credential_id)
        return resolved


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
    owner_user_id: Optional[UUID] = None  # 소유자(creator). DB schema는 NOT NULL이라 Repository.save 시점에 필수 — Optional은 점진 마이그레이션/역직렬화 호환용
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
