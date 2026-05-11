from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "anthropic_chat"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class AnthropicChatInput:
    model: str                                                  # e.g. "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"
    messages: list[dict[str, Any]]                              # [{"role": "user", "content": "..."}, ...]
    max_tokens: int = 1024
    system: str | None = None                                   # system prompt
    temperature: float = 1.0
    top_p: float = 1.0
    stop_sequences: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AnthropicChatOutput:
    content: str                                                # text content (멀티 블록은 결합)
    stop_reason: str                                            # end_turn | max_tokens | stop_sequence | tool_use
    model: str
    usage: dict[str, int]                                       # {"input_tokens": .., "output_tokens": ..}
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

    async def process(self, input: AnthropicChatInput) -> AnthropicChatOutput:
        raise NotImplementedError(
            "Anthropic API 호출은 REQ-005 toolset connector를 통해 처리. "
            "API key 주입은 REQ-002 CredentialInjectionService 담당."
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
                "model": {"type": "string"},
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["user", "assistant"]},
                            "content": {},
                        },
                        "required": ["role", "content"],
                    },
                },
                "max_tokens": {"type": "integer", "default": 1024},
                "system": {"type": ["string", "null"]},
                "temperature": {"type": "number", "default": 1.0, "minimum": 0, "maximum": 1},
                "top_p": {"type": "number", "default": 1.0},
                "stop_sequences": {"type": "array", "items": {"type": "string"}},
                "tools": {"type": "array", "items": {"type": "object"}},
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
