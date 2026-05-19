from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    name: str | None = None


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str | None
    tool_calls: list[ToolCall] = []
    finish_reason: Literal["stop", "tool_calls", "length"]
