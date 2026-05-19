from common_schemas.transport import LLMResponse, Message, ToolCall


class TestMessage:
    def test_user_message(self):
        m = Message(role="user", content="hello")
        assert m.role == "user"
        assert m.content == "hello"
        assert m.tool_call_id is None
        assert m.name is None

    def test_tool_message(self):
        m = Message(role="tool", content='{"ok": true}', tool_call_id="call_1", name="rest_api")
        assert m.role == "tool"
        assert m.tool_call_id == "call_1"
        assert m.name == "rest_api"

    def test_frozen(self):
        import pytest
        from pydantic import ValidationError

        m = Message(role="user", content="x")
        with pytest.raises(ValidationError):
            m.content = "y"


class TestToolCall:
    def test_create(self):
        call = ToolCall(id="call_1", name="rest_api", arguments={"url": "https://x.com"})
        assert call.id == "call_1"
        assert call.name == "rest_api"
        assert call.arguments == {"url": "https://x.com"}

    def test_empty_arguments(self):
        call = ToolCall(id="call_2", name="health_check", arguments={})
        assert call.arguments == {}


class TestLLMResponse:
    def test_content_only(self):
        r = LLMResponse(content="answer", finish_reason="stop")
        assert r.content == "answer"
        assert r.tool_calls == []
        assert r.finish_reason == "stop"

    def test_with_tool_calls(self):
        call = ToolCall(id="call_1", name="rest_api", arguments={"url": "https://x.com"})
        r = LLMResponse(content=None, tool_calls=[call], finish_reason="tool_calls")
        assert r.content is None
        assert len(r.tool_calls) == 1
        assert r.finish_reason == "tool_calls"

    def test_length_truncated(self):
        r = LLMResponse(content="partial...", finish_reason="length")
        assert r.finish_reason == "length"
