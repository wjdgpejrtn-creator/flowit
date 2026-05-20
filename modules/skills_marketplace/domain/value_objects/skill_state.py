from __future__ import annotations

from enum import Enum


class SkillState(str, Enum):
    """스킬 게시 상태 (storage/marketplace에서 이전 — ADR-0012 PR-2d).

    범위 승격(SkillScope: personal→team→company)과는 별개 축인 게시 lifecycle 상태.
    전이 규칙은 `domain/services/skill_lifecycle.py`의 SkillLifecycle이 담당.
    str 상속으로 JSON 직렬화 호환 (CLAUDE.md 컨벤션).
    """

    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"
