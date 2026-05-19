"""PersonalSkill — Personalization Agent가 GCS memory.md에서 관리하는 사용자 패턴 단위.

REQ-004 spec §2.1 정의.
skill_type은 Claude Code memory.md 패턴을 그대로 따른다:
  user / feedback / project / reference
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from common_schemas import UtcDatetime
from pydantic import BaseModel, ConfigDict, Field


class PersonalSkill(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    skill_type: Literal["user", "feedback", "project", "reference"]
    name: str
    description: str
    body: str
    embedding: Optional[list[float]] = None  # BGE-M3 768d
    updated_at: UtcDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
