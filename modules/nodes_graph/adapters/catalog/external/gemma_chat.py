from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

_NODE_TYPE = "gemma_chat"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_TIMEOUT_SECONDS = 120  # Modal cold start + 추론 — 넉넉히


@dataclass
class GemmaChatInput:
    prompt: str  # Composer가 동적 생성한 prompt
    response_format: str = "text"  # "text" | "json" | "markdown"
    max_tokens: int = 1024
    temperature: float = 0.7
    system: str | None = None  # system prompt (선택)


@dataclass
class GemmaChatOutput:
    content: str  # 생성된 텍스트
    finish_reason: str  # stop | max_tokens
    usage: dict[str, int]  # {"input_tokens": .., "output_tokens": ..}


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

    async def process(self, input: GemmaChatInput, context: NodeContext) -> GemmaChatOutput:
        # 시스템 내장 LLM — credential 불필요. llm-base의 /v1/generate HTTP 경로 호출
        # (Modal SDK 의존 없이 httpx만 사용). LLM_BASE_URL은 worker secret_env_vars로 주입.
        base_url = os.getenv("LLM_BASE_URL", "").rstrip("/")
        if not base_url:
            raise ExecutionError("gemma_chat: LLM_BASE_URL 환경변수 미설정")

        body: dict[str, Any] = {
            "prompt": input.prompt,
            "max_tokens": input.max_tokens,
            "temperature": input.temperature,
        }
        if input.system:
            body["system"] = input.system
        if input.response_format == "json":
            body["format"] = "json"

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{base_url}/v1/generate", json=body)

        if response.status_code >= 400:
            raise ExecutionError(f"llm-base /v1/generate 오류 {response.status_code}: {response.text[:200]}")

        data = response.json()
        return GemmaChatOutput(
            content=data.get("generated_text", ""),
            finish_reason=data.get("finish_reason", ""),
            usage=data.get("usage", {}),
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
                "prompt": {"type": "string", "description": "Gemma 모델에 보낼 입력 프롬프트"},
                "response_format": {
                    "type": "string",
                    "enum": ["text", "json", "markdown"],
                    "default": "text",
                    "description": "응답 형식. text=일반텍스트, json=JSON, markdown=마크다운. 기본값 text",
                },
                "max_tokens": {"type": "integer", "default": 1024, "description": "생성할 최대 토큰 수. 기본값 1024"},
                "temperature": {
                    "type": "number",
                    "default": 0.7,
                    "minimum": 0,
                    "maximum": 2,
                    "description": "출력 무작위성(0=결정적, 1=다양). 기본값 0.7",
                },
                "system": {"type": ["string", "null"], "description": "모델 동작을 지시하는 시스템 프롬프트(선택)"},
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
            "Gemma 4 LLM 추론 (시스템 내장, 자격증명 불필요). prompt → 텍스트 응답. REQ-004 ModalLLMAdapter 위임."
        ),
        is_mvp=True,
        service_type="gemma",
    )
