"""SkillNode — Skills Builder가 추출/로드한 단일 스킬 표현.

REQ-004 spec §2.1 정의 + 직무 영역 source 확장 (2026-05-12 조장 합의).

flow:
    SOP DocumentBlock / industry default seed JSON / functional domain default seed JSON
        → SkillNode (검증 단위)
        → NodeDefinition (카탈로그 저장 형태)
        → nodes_graph.NodeDefinitionRepository.upsert()

source_type 분류:
- "sop"               — SOP 문서에서 LLM이 추출한 SkillNode (BuildFromSOPUseCase)
- "industry_default"  — 산업별 표준 seed에서 로드 (BuildFromIndustryDefaultUseCase)
                        활성: ecommerce / 비활성: manufacturing·service·wholesale_retail·food·it
- "functional_domain" — 직무 영역별 표준 seed에서 로드 (BuildFromFunctionalDomainUseCase)
                        활성: customer_support / it_ops / document_data / hr / marketing
"""
from __future__ import annotations

from typing import Any, Literal

from common_schemas.enums import RiskLevel
from pydantic import BaseModel, ConfigDict, Field


class SkillNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_type: Literal["sop", "industry_default", "functional_domain"]
    source_id: str                                  # SOP 문서 ID / 산업 코드 / 직무 영역 코드
    name: str                                       # 사람이 읽을 수 있는 이름
    description: str                                # 노드 설명
    inputs: dict[str, Any] = Field(default_factory=dict)    # JSON Schema
    outputs: dict[str, Any] = Field(default_factory=dict)   # JSON Schema
    risk_level: RiskLevel
