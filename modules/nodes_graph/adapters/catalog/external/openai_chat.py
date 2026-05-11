from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "openai_chat"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class OpenaiChatInput:
    model: str                                                  # e.g. "gpt-4o", "gpt-4o-mini"
    messages: list[dict[str, str]]                              # [{"role": "user", "content": "..."}, ...]
    temperature: float = 1.0
    max_tokens: int | None = None
    top_p: float = 1.0
    response_format: dict[str, Any] | None = None               # {"type": "json_object"} 등
    seed: int | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)   # function calling


@dataclass
class OpenaiChatOutput:
    content: str
    finish_reason: str                                          # stop | length | tool_calls | content_filter
    model: str                                                  # 실제 사용된 모델
    usage: dict[str, int]                                       # {"prompt_tokens": .., "completion_tokens": .., "total_tokens": ..}
    tool_calls: list[dict[str, Any]]


class OpenaiChatNode(BaseNode[OpenaiChatInput, OpenaiChatOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="OpenAI Chat",
        category="AI / LLM",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = OpenaiChatInput
    output_schema = OpenaiChatOutput

    async def process(self, input: OpenaiChatInput) -> OpenaiChatOutput:
        raise NotImplementedError(
            "OpenAI API 호출은 REQ-005 toolset connector를 통해 처리. "
            "API key 주입은 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="OpenAI Chat",
        category="AI / LLM",
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
                            "role": {"type": "string", "enum": ["system", "user", "assistant", "tool"]},
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                    },
                },
                "temperature": {"type": "number", "default": 1.0, "minimum": 0, "maximum": 2},
                "max_tokens": {"type": ["integer", "null"]},
                "top_p": {"type": "number", "default": 1.0},
                "response_format": {"type": ["object", "null"]},
                "seed": {"type": ["integer", "null"]},
                "tools": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["model", "messages"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "finish_reason": {"type": "string"},
                "model": {"type": "string"},
                "usage": {"type": "object"},
                "tool_calls": {"type": "array", "items": {"type": "object"}},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["openai"],
        description="OpenAI Chat Completions API 호출 (gpt-4o, gpt-4o-mini 등). API key 자격증명 필요",
        is_mvp=True,
        service_type="openai",
    )
