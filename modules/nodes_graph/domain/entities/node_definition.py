from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from common_schemas.enums import RiskLevel


@dataclass
class NodeDefinition:
    """62종 노드 타입의 카탈로그 엔티티.

    H-4 합의: REQ-002 CredentialInjectionService가 get_by_id() 후
    risk_level, required_connections, service_type 필드에 직접 접근한다.
    """

    # NodeConfig 동일 필드 (REQ-012 참조)
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

    # REQ-003 확장 필드
    service_type: str | None = None
    embedding: list[float] | None = None

    # ADR-0020 (i) scope 격리. None=company 전역(기존 62종 비침습) / owner=personal / team=team
    owner_user_id: UUID | None = None
    team_id: UUID | None = None
