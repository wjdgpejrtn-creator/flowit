"""LLM 2종 + Linear 1종 외부 노드 process() unit test (ADR-0018 Phase 3c).

httpx.AsyncClient를 fake로 치환해 검증.
- anthropic_chat: Anthropic Messages API (connection_token = API key)
- linear_create_issue: Linear GraphQL issueCreate (connection_token = API key)
- gemma_chat: llm-base /v1/generate (credential 불필요, LLM_BASE_URL 기반)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx
import pytest
from common_schemas import NodeContext
from common_schemas.exceptions import ExecutionError, ValidationError

from nodes_graph.adapters.catalog.external.anthropic_chat import (
    AnthropicChatInput,
    AnthropicChatNode,
)
from nodes_graph.adapters.catalog.external.gemma_chat import GemmaChatInput, GemmaChatNode
from nodes_graph.adapters.catalog.external.linear_create_issue import (
    LinearCreateIssueInput,
    LinearCreateIssueNode,
)

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())


def _ctx_with_token(token: str) -> NodeContext:
    return NodeContext(execution_id=uuid4(), user_id=uuid4(), connection_token=token)


@dataclass
class _FakeResponse:
    status_code: int = 200
    json_body: Any = field(default_factory=dict)
    text: str = ""

    def json(self) -> Any:
        return self.json_body


class _HttpController:
    def __init__(self) -> None:
        self.response = _FakeResponse()
        self.request: dict | None = None


@pytest.fixture
def fake_http(monkeypatch):
    ctrl = _HttpController()

    class _FakeClient:
        def __init__(self, **kwargs) -> None:
            ctrl.client_kwargs = kwargs

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def post(self, url, **kwargs):
            ctrl.request = {"url": url, **kwargs}
            return ctrl.response

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _FakeClient(**kw))
    return ctrl


# ----------------------------------------------------------------------
# anthropic_chat
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anthropic_chat_success_combines_text_and_tool_use(fake_http):
    fake_http.response = _FakeResponse(
        200,
        {
            "content": [
                {"type": "text", "text": "안녕 "},
                {"type": "text", "text": "아름"},
                {"type": "tool_use", "id": "t1", "name": "calc", "input": {"x": 1}},
            ],
            "stop_reason": "tool_use",
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 12, "output_tokens": 8},
        },
    )
    out = await AnthropicChatNode().process(
        AnthropicChatInput(model="claude-opus-4-7", messages=[{"role": "user", "content": "hi"}]),
        _ctx_with_token("sk-ant-test"),
    )
    assert out.content == "안녕 아름"
    assert out.stop_reason == "tool_use"
    assert out.usage == {"input_tokens": 12, "output_tokens": 8}
    assert len(out.tool_use) == 1 and out.tool_use[0]["name"] == "calc"
    assert fake_http.request["headers"]["x-api-key"] == "sk-ant-test"
    assert fake_http.request["headers"]["anthropic-version"]


@pytest.mark.asyncio
async def test_anthropic_chat_missing_token_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await AnthropicChatNode().process(
            AnthropicChatInput(model="claude-opus-4-7", messages=[]), NODE_CTX
        )


@pytest.mark.asyncio
async def test_anthropic_chat_api_error_raises(fake_http):
    fake_http.response = _FakeResponse(401, text='{"error": "invalid x-api-key"}')
    with pytest.raises(ExecutionError, match="Anthropic API 오류 401"):
        await AnthropicChatNode().process(
            AnthropicChatInput(model="claude-opus-4-7", messages=[]),
            _ctx_with_token("bad-key"),
        )


# ----------------------------------------------------------------------
# linear_create_issue
# ----------------------------------------------------------------------


def _linear_ok_response() -> _FakeResponse:
    return _FakeResponse(
        200,
        {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "issue-uuid",
                        "identifier": "ENG-42",
                        "url": "https://linear.app/x/issue/ENG-42",
                        "title": "버그 수정",
                        "state": {"name": "Backlog"},
                        "createdAt": "2026-05-21T00:00:00.000Z",
                    },
                }
            }
        },
    )


@pytest.mark.asyncio
async def test_linear_create_issue_success(fake_http):
    fake_http.response = _linear_ok_response()
    out = await LinearCreateIssueNode().process(
        LinearCreateIssueInput(team_id="team-1", title="버그 수정", priority=2),
        _ctx_with_token("lin_api_test"),
    )
    assert out.issue_id == "issue-uuid"
    assert out.identifier == "ENG-42"
    assert out.state == "Backlog"
    assert fake_http.request["headers"]["Authorization"] == "lin_api_test"
    assert fake_http.request["json"]["variables"]["input"]["teamId"] == "team-1"
    assert fake_http.request["json"]["variables"]["input"]["priority"] == 2


@pytest.mark.asyncio
async def test_linear_create_issue_missing_token_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await LinearCreateIssueNode().process(
            LinearCreateIssueInput(team_id="t", title="x"), NODE_CTX
        )


@pytest.mark.asyncio
async def test_linear_create_issue_graphql_error_raises(fake_http):
    fake_http.response = _FakeResponse(200, {"errors": [{"message": "auth failed"}]})
    with pytest.raises(ExecutionError, match="GraphQL"):
        await LinearCreateIssueNode().process(
            LinearCreateIssueInput(team_id="t", title="x"), _ctx_with_token("bad")
        )


@pytest.mark.asyncio
async def test_linear_create_issue_unsuccessful_raises(fake_http):
    fake_http.response = _FakeResponse(200, {"data": {"issueCreate": {"success": False}}})
    with pytest.raises(ExecutionError, match="실패"):
        await LinearCreateIssueNode().process(
            LinearCreateIssueInput(team_id="t", title="x"), _ctx_with_token("key")
        )


# ----------------------------------------------------------------------
# gemma_chat
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemma_chat_success(fake_http, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://93.184.216.34")
    fake_http.response = _FakeResponse(
        200,
        {
            "generated_text": "생성된 응답",
            "finish_reason": "stop",
            "usage": {"input_tokens": 5, "output_tokens": 9},
        },
    )
    out = await GemmaChatNode().process(
        GemmaChatInput(prompt="요약해줘", response_format="json"), NODE_CTX
    )
    assert out.content == "생성된 응답"
    assert out.finish_reason == "stop"
    assert out.usage == {"input_tokens": 5, "output_tokens": 9}
    assert fake_http.request["url"] == "http://93.184.216.34/v1/generate"
    assert fake_http.request["json"]["format"] == "json"  # response_format=json → format


@pytest.mark.asyncio
async def test_gemma_chat_text_format_omits_json_mode(fake_http, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://93.184.216.34")
    fake_http.response = _FakeResponse(200, {"generated_text": "x", "finish_reason": "stop"})
    await GemmaChatNode().process(GemmaChatInput(prompt="hi"), NODE_CTX)
    assert "format" not in fake_http.request["json"]  # response_format=text(기본) → format 미전송


@pytest.mark.asyncio
async def test_gemma_chat_missing_base_url_raises(fake_http, monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    with pytest.raises(ExecutionError, match="LLM_BASE_URL"):
        await GemmaChatNode().process(GemmaChatInput(prompt="hi"), NODE_CTX)
