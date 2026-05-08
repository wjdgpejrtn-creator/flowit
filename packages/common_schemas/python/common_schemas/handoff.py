from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class HandoffPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    handoff_type: Literal["recovery_mode", "result_review"]
    direction: Literal["forward", "reverse"]
    error_codes: list[str]
    error_messages: list[str]
    state_data: dict[str, Any]
    correlation_id: UUID


class EvaluationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: float
    pass_flag: bool
    reason: str
    feedback: str
