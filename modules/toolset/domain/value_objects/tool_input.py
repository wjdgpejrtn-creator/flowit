from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolInput:
    data: dict[str, Any]
    schema_version: str = "draft-7"
