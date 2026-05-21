from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SkillDocument(BaseModel):
    """스킬 지침서 (SkillsMP SKILL.md 레퍼런스 — ADR-0017).

    한 스킬의 이중 저장 중 "지침서" 측 (메타는 NodeDefinition + SkillRepository).
    LLM(Main Agent)이 사용자에게 옵션 제시 시 자연어로 읽는 markdown 문서.
    저장: GCS (`gs://{bucket}/skills/{skill_id}/SKILL.md`) via SkillDocumentStore.

    SSOT: common_schemas (PR #106 리뷰 결정 — 생산자 ai_agent + 저장자
    skills_marketplace 양쪽이 쓰는 공유 타입이라 import 규칙 위반 없이 type-safe
    하게 공유하기 위해 ADR-0017의 skills_marketplace 도메인 소유에서 정정).

    SKILL.md 직렬화 형태::

        ---
        name: {name}
        description: {description}
        ---
        {instructions}   # markdown body (When to use / Step-by-step / Inputs·Outputs)
    """

    model_config = ConfigDict(frozen=True)

    skill_id: UUID
    name: str  # frontmatter — 사람이 읽는 스킬 이름 (Main Agent가 옵션 제시 시 표시). 식별자는 skill_id.
    description: str  # frontmatter — LLM trigger 판단용 자연어
    instructions: str  # markdown body — 단계별 지침서
    scripts: list[dict[str, Any]] = Field(default_factory=list)  # 선택 — SKILL.md scripts/ (path/content)
    templates: list[dict[str, Any]] = Field(default_factory=list)  # 선택 — SKILL.md templates/
