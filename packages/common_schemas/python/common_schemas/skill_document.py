from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SkillDocument(BaseModel):
    """스킬 지침서 묶음 (SkillsMP — ADR-0017, #372 이중 정체성 해소).

    한 스킬의 이중 저장 중 "지침서" 측 (메타는 NodeDefinition + SkillRepository).
    스킬은 **두 소비처가 완전히 다른** 지침서를 가질 수 있다(#372 합의 — 스킬=지침서 묶음):

    - ``instructions`` (SKILL.md) — **노드측**. execution_engine `CatalogNodeExecutor._inject_skill`이
      실행 시 바인딩된 LLM 노드 system 프롬프트에 주입(REQ-013). "이 작업을 어떻게 수행하는가".
    - ``composer_instructions`` (COMPOSER.md) — **composer측**. ai_agent drafter가 워크플로우 생성 시
      주입(신규). "이 스킬을 쓰려면 어떤 노드를 어떻게 엮어야 하는가"(예: LLM 노드 + Email 노드 필수).
      이게 명시되면 drafter가 LLM 노드를 포함해 바인딩이 성립(#372 결함 A 해소).

    둘 다 optional — 노드 지침만 있는 스킬, composer 지침만 있는 스킬 모두 가능(#372 detail 3).
    저장: GCS `skills/{skill_id}/SKILL.md` + `skills/{skill_id}/COMPOSER.md` via SkillDocumentStore.

    SSOT: common_schemas (PR #106 리뷰 결정 — 생산자 ai_agent + 저장자
    skills_marketplace 양쪽이 쓰는 공유 타입이라 import 규칙 위반 없이 type-safe
    하게 공유하기 위해 ADR-0017의 skills_marketplace 도메인 소유에서 정정).

    SKILL.md 직렬화 형태::

        ---
        name: {name}
        description: {description}
        ---
        {instructions}   # markdown body (When to use / Step-by-step / Inputs·Outputs)

    COMPOSER.md 직렬화 형태:: 프론트matter 없이 ``composer_instructions`` 본문만(name/description은
    SKILL.md가 보유). 비어 있으면 파일을 쓰지 않는다(부재 시 load에서 "").
    """

    model_config = ConfigDict(frozen=True)

    skill_id: UUID
    name: str  # frontmatter — 사람이 읽는 스킬 이름 (Main Agent가 옵션 제시 시 표시). 식별자는 skill_id.
    description: str  # frontmatter — LLM trigger 판단용 자연어
    instructions: str = ""  # SKILL.md body — 노드측 단계별 지침서 (optional, #372)
    composer_instructions: str = ""  # COMPOSER.md body — composer측 노드 구성 지침서 (optional, #372)
    scripts: list[dict[str, Any]] = Field(default_factory=list)  # 선택 — SKILL.md scripts/ (path/content)
    templates: list[dict[str, Any]] = Field(default_factory=list)  # 선택 — SKILL.md templates/
