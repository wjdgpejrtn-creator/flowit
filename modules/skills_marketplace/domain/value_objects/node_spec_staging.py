from __future__ import annotations

from typing import Any

from common_schemas.enums import RiskLevel
from pydantic import BaseModel, ConfigDict, Field


class NodeSpecStaging(BaseModel):
    """publish 전 노드 스펙 임시 보관 (ADR-0020 Q1).

    Skills Builder 추출 결과를 MarketplaceSkill DRAFT에 보관한다. NodeDefinition은
    `lifecycle_state == PUBLISHED` 시점에만 생성하므로(ADR-0020 Option B), 그 전까지
    노드 스펙(`nodes_graph.NodeDefinition`의 입력에 해당하는 필드)을 여기 staging한다.
    publish 시 이 staging + MarketplaceSkill 메타(name/description/embedding/owner/team)를
    합쳐 NodeDefinition을 생성·upsert한다.
    """

    model_config = ConfigDict(frozen=True)

    category: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: RiskLevel
    required_connections: list[str] = Field(default_factory=list)
    service_type: str | None = None
