from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolOutput:
    data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
