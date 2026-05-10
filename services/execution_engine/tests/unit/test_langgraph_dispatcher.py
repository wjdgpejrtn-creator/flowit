"""LangGraphDispatcher 단위 테스트 — AI 에이전트 노드 실행."""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from common_schemas.enums import RiskLevel
from common_schemas.workflow import NodeConfig, NodeInstance, Position

from src.adapters.langgraph_dispatcher import LangGraphDispatcher


def _make_node():
    return NodeInstance(
        instance_id=uuid4(),
        node_id=uuid4(),
        parameters={"prompt": "summarize this"},
        position=Position(x=0, y=0),
    )


def _make_config(node_type="text_summarizer"):
    return NodeConfig(
        node_id=uuid4(),
        node_type=node_type,
        name="Text Summarizer",
        category="ai",
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="텍스트 요약",
        is_mvp=True,
    )


class TestLangGraphDispatcher:
    def test_invokes_graph_with_correct_name(self):
        mock_fn = MagicMock(return_value={"summary": "result"})
        dispatcher = LangGraphDispatcher(invoke_graph=mock_fn)
        node = _make_node()
        config = _make_config("text_summarizer")

        result = dispatcher.execute(node, config, {"doc": "content"})

        mock_fn.assert_called_once()
        call_kwargs = mock_fn.call_args[1]
        assert call_kwargs["graph_name"] == "text_summarizer"
        assert result == {"summary": "result"}

    def test_passes_node_parameters(self):
        mock_fn = MagicMock(return_value={})
        dispatcher = LangGraphDispatcher(invoke_graph=mock_fn)
        node = _make_node()
        config = _make_config()

        dispatcher.execute(node, config, {})

        call_kwargs = mock_fn.call_args[1]
        assert call_kwargs["inputs"]["parameters"]["prompt"] == "summarize this"

    def test_strips_credentials_from_inputs(self):
        mock_fn = MagicMock(return_value={})
        dispatcher = LangGraphDispatcher(invoke_graph=mock_fn)
        node = _make_node()
        config = _make_config()

        dispatcher.execute(node, config, {"__credentials__": {"key": "secret"}, "data": "ok"})

        call_kwargs = mock_fn.call_args[1]
        assert "__credentials__" not in call_kwargs["inputs"]
        assert call_kwargs["inputs"]["data"] == "ok"

    def test_includes_node_instance_id(self):
        mock_fn = MagicMock(return_value={})
        dispatcher = LangGraphDispatcher(invoke_graph=mock_fn)
        node = _make_node()
        config = _make_config()

        dispatcher.execute(node, config, {})

        call_kwargs = mock_fn.call_args[1]
        assert call_kwargs["inputs"]["node_instance_id"] == str(node.instance_id)
