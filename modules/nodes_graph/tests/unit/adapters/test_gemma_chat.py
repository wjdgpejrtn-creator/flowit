"""gemma_chat 노드 카탈로그 정의 + process() 위임 contract 검증.

REQ-003 카탈로그 노드 = AI 에이전트(REQ-004 Composer)가 자동 선택하는 빌딩 블록.
gemma_chat은 시스템 내장 Gemma 4 LLM wrapper — prompt 동적 입력 + 자격증명 불필요.
실제 LLM 추론은 REQ-004 ai_agent.adapters.llm.ModalLLMAdapter가 담당.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError

from nodes_graph.adapters.catalog.external.gemma_chat import (
    GemmaChatInput,
    GemmaChatNode,
    get_node_definition,
)

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())


def test_node_definition_identity_fields():
    definition = get_node_definition()
    assert definition.node_type == "gemma_chat"
    assert definition.name == "Gemma Chat"
    assert definition.category == "ai"
    assert definition.version == "1.0.0"
    assert definition.is_mvp is True


def test_node_definition_system_internal_no_credentials():
    """시스템 내장 LLM — required_connections=[], risk_level=LOW."""
    definition = get_node_definition()
    assert definition.required_connections == []
    assert definition.risk_level == RiskLevel.LOW
    assert definition.service_type == "gemma"


def test_input_schema_prompt_required():
    definition = get_node_definition()
    assert "prompt" in definition.input_schema["required"]


def test_input_schema_response_format_enum():
    definition = get_node_definition()
    response_format = definition.input_schema["properties"]["response_format"]
    assert response_format["enum"] == ["text", "json", "markdown"]
    assert response_format["default"] == "text"


def test_output_schema_fields():
    definition = get_node_definition()
    output_props = definition.output_schema["properties"]
    assert "content" in output_props
    assert "finish_reason" in output_props
    assert "usage" in output_props


def test_metadata_consistent_with_definition():
    node = GemmaChatNode()
    definition = get_node_definition()
    assert node.metadata.node_id == definition.node_id
    assert node.metadata.name == definition.name
    assert node.metadata.category == definition.category
    assert node.metadata.risk_level == definition.risk_level


@pytest.mark.asyncio
async def test_process_requires_llm_base_url(monkeypatch):
    """gemma_chat은 ADR-0018 Phase 3c에서 실구현 — llm-base /v1/generate HTTP 호출.
    LLM_BASE_URL 미설정 시 ExecutionError. 실행 경로 전체는 test_llm_linear_nodes.py 참조."""
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    node = GemmaChatNode()
    with pytest.raises(ExecutionError, match="LLM_BASE_URL"):
        await node.process(GemmaChatInput(prompt="테스트 prompt"), NODE_CTX)
