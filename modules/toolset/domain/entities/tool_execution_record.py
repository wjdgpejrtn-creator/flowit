from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID, uuid4


@dataclass
class ToolExecutionRecord:
    tool_id: str
    input_data: dict
    status: Literal["success", "failed", "timeout"]
    duration_ms: int
    executed_at: datetime = field(default_factory=datetime.utcnow)
    execution_id: UUID = field(default_factory=uuid4)
    output_data: Optional[dict] = None
    error_message: Optional[str] = None

    def is_successful(self) -> bool:
        return self.status == "success"
