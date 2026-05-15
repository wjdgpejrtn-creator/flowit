from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "gemma_chat"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class GemmaChatInput:
    prompt: str                                                 # Composer가 동적 생성한 prompt
    response_format: str = "text"                               # "text" | "json" | "markdown"
    max_tokens: int = 1024
    temperature: float = 0.7
    system: str | None = None                                   # system prompt (선택)


@dataclass
class GemmaChatOutput:
    content: str                                                # 생성된 텍스트
    finish_reason: str                                          # stop | max_tokens
    usage: dict[str, int]                                       # {"input_tokens": .., "output_tokens": ..}


class GemmaChatNode(BaseNode[GemmaChatInput, GemmaChatOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Gemma Chat",
        category="ai",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = GemmaChatInput
    output_schema = GemmaChatOutput

    async def process(self, input: GemmaChatInput) -> GemmaChatOutput:
        raise NotImplementedError(
            "Gemma 4 추론은 REQ-004 ai_agent ModalLLMAdapter를 통해 처리. "
            "Modal llm-base RPC 호출 (자격증명 불필요 — 시스템 내장 LLM)."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Gemma Chat",
        category="ai",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "response_format": {
                    "type": "string",
                    "enum": ["text", "json", "markdown"],
                    "default": "text",
                },
                "max_tokens": {"type": "integer", "default": 1024},
                "temperature": {"type": "number", "default": 0.7, "minimum": 0, "maximum": 2},
                "system": {"type": ["string", "null"]},
            },
            "required": ["prompt"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "finish_reason": {"type": "string"},
                "usage": {"type": "object"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description=(
            "Gemma 4 LLM 추론 (시스템 내장, 자격증명 불필요). "
            "prompt → 텍스트 응답. REQ-004 ModalLLMAdapter 위임."
        ),
        is_mvp=True,
        service_type="gemma",
    )
