"""SkillNode — Skills Builder가 추출/로드한 단일 스킬 표현.

REQ-004 spec §2.1 정의.

flow:
    SOP DocumentBlock / industry default seed JSON
        → SkillNode (검증 단위)
        → NodeDefinition (카탈로그 저장 형태)
        → nodes_graph.NodeDefinitionRepository.upsert()
"""
from __future__ import annotations

from typing import Any, Literal

from common_schemas.enums import RiskLevel
from pydantic import BaseModel, ConfigDict, Field


class SkillNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_type: Literal["sop", "industry_default"]
    source_id: str                                  # SOP 문서 ID 또는 산업 코드 (manufacturing/service/...)
    name: str                                       # 사람이 읽을 수 있는 이름
    description: str                                # 노드 설명
    inputs: dict[str, Any] = Field(default_factory=dict)    # JSON Schema
    outputs: dict[str, Any] = Field(default_factory=dict)   # JSON Schema
    risk_level: RiskLevel
