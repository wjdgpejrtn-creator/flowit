from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from .enums import ErrorCode


class ValidationErrorItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str
    node_ids: list[str]
    edge_id: Optional[str] = None
    validator: Literal["SchemaValidation", "RuntimeValidation"]
    hint: Optional[str] = None


class ValidationErrorResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    validation_status: Literal["passed", "failed"]
    errors: list[ValidationErrorItem]
