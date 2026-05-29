from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryFileType = Literal["user", "feedback", "project", "reference"]


class MemoryFileRef(BaseModel):
    """MEMORY.md 인덱스의 단일 항목."""

    model_config = ConfigDict(frozen=True)

    filename: str
    name: str
    description: str


class MemoryFile(BaseModel):
    """GCS .md 파일 전체 표현 (frontmatter + body)."""

    model_config = ConfigDict(frozen=True)

    filename: str
    name: str
    description: str
    memory_type: MemoryFileType
    body: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
