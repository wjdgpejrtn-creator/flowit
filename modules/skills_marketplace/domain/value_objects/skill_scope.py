from __future__ import annotations

from enum import Enum


class SkillScope(str, Enum):
    """스킬 공개 범위 3계층 (ADR-0012 v3).

    승격 흐름: PERSONAL → TEAM → COMPANY (단방향).
    str 상속으로 JSON 직렬화 호환 (CLAUDE.md 컨벤션).
    """

    PERSONAL = "personal"
    TEAM = "team"
    COMPANY = "company"
