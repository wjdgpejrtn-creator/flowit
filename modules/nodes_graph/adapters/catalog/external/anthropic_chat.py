from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError, ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

_NODE_TYPE = "anthropic_chat"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_TIMEOUT_SECONDS = 120  # LLM 추론은 느림 — 넉넉히


@dataclass
class AnthropicChatInput:
    model: str  # 예: claude-opus-4-7 / claude-sonnet-4-6 / claude-haiku-4-5
    messages: list[dict[str, Any]]  # [{"role": "user", "content": "..."}, ...]
    max_tokens: int = 1024
    system: str | None = None  # system prompt
    temperature: float = 1.0
    top_p: float = 1.0
    stop_sequences: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AnthropicChatOutput:
    content: str  # text content (멀티 블록은 결합)
    stop_reason: str  # end_turn | max_tokens | stop_sequence | tool_use
    model: str
    usage: dict[str, int]  # {"input_tokens": .., "output_tokens": ..}
    tool_use: list[dict[str, Any]]


class AnthropicChatNode(BaseNode[AnthropicChatInput, AnthropicChatOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Anthropic Chat",
        category="ai",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = AnthropicChatInput
    output_schema = AnthropicChatOutput

    async def process(self, input: AnthropicChatInput, context: NodeContext) -> AnthropicChatOutput:
        # connection_token = Anthropic API key (x-api-key 헤더).
        if not context.connection_token:
            raise ValidationError("anthropic_chat는 credential(Anthropic API key)이 필요하다")

        body: dict[str, Any] = {
            "model": input.model,
            "messages": input.messages,
            "max_tokens": input.max_tokens,
            "temperature": input.temperature,
            "top_p": input.top_p,
        }
        if input.system:
            body["system"] = input.system
        if input.stop_sequences:
            body["stop_sequences"] = input.stop_sequences
        if input.tools:
            body["tools"] = input.tools
        headers = {
            "x-api-key": context.connection_token,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_ANTHROPIC_API_URL, json=body, headers=headers)

        if response.status_code >= 400:
            raise ExecutionError(f"Anthropic API 오류 {response.status_code}: {response.text[:200]}")

        data = response.json()
        blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        tool_use = [b for b in blocks if b.get("type") == "tool_use"]
        return AnthropicChatOutput(
            content=text,
            stop_reason=data.get("stop_reason", ""),
            model=data.get("model", input.model),
            usage=data.get("usage", {}),
            tool_use=tool_use,
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Anthropic Chat",
        category="ai",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": '사용할 Claude 모델 ID. 예: "claude-opus-4-8", "claude-sonnet-4-6"',
                },
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"role": {"type": "string", "enum": ["user", "assistant"]}, "content": {}},
                        "required": ["role", "content"],
                    },
                    "description": "대화 메시지 목록. 각 항목은 role(user/assistant)과 content",
                },
                "max_tokens": {"type": "integer", "default": 1024, "description": "생성할 최대 토큰 수. 기본값 1024"},
                "system": {"type": ["string", "null"], "description": "모델 동작을 지시하는 시스템 프롬프트(선택)"},
                "temperature": {
                    "type": "number",
                    "default": 1.0,
                    "minimum": 0,
                    "maximum": 1,
                    "description": "출력 무작위성(0=결정적, 1=다양). 기본값 1.0",
                },
                "top_p": {"type": "number", "default": 1.0, "description": "누적 확률 샘플링 기준(0~1). 기본값 1.0"},
                "stop_sequences": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "생성을 중단할 문자열 목록(선택)",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "모델이 호출할 수 있는 도구 정의 목록(선택)",
                },
            },
            "required": ["model", "messages"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "stop_reason": {"type": "string"},
                "model": {"type": "string"},
                "usage": {"type": "object"},
                "tool_use": {"type": "array", "items": {"type": "object"}},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["anthropic"],
        description="Anthropic Messages API 호출 (Claude opus/sonnet/haiku). API key 자격증명 필요",
        is_mvp=True,
        service_type="anthropic",
    )
