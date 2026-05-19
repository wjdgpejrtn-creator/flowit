from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from toolset.adapters.internal.api.graphql_tool import GraphqlTool
from toolset.adapters.internal.api.http_request_tool import HttpRequestTool
from toolset.adapters.internal.api.rest_api_tool import RestApiTool
from toolset.adapters.internal.api.webhook_tool import WebhookTool
from toolset.domain.exceptions import ToolExecutionError
from toolset.domain.value_objects.connector_response import ConnectorResponse


# ── HttpRequestTool ───────────────────────────────────────────────────────────

class TestHttpRequestTool:
    @pytest.mark.asyncio
    async def test_get_request_success(self):
        tool = HttpRequestTool()
        mock_resp = MagicMock()
        mock_resp.content = json.dumps({"hello": "world"}).encode()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await tool.execute({"url": "https://example.com/api"})

        assert result["status_code"] == 200
        assert result["body"] == {"hello": "world"}

    @pytest.mark.asyncio
    async def test_post_with_body(self):
        tool = HttpRequestTool()
        mock_resp = MagicMock()
        mock_resp.content = b'{"id": 1}'
        mock_resp.status_code = 201
        mock_resp.headers = {}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await tool.execute({"url": "https://api.example.com", "method": "POST", "body": {"name": "test"}})

        assert result["status_code"] == 201

    @pytest.mark.asyncio
    async def test_uses_connector_when_provided(self):
        tool = HttpRequestTool()
        mock_connector = AsyncMock()
        mock_credential = MagicMock()
        mock_connector.connect.return_value = ConnectorResponse(
            status_code=200, body=b'{"ok": true}', headers={}
        )

        result = await tool.execute(
            {"url": "https://secure.api"},
            connector=mock_connector,
            credential=mock_credential,
        )

        mock_connector.connect.assert_called_once()
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_non_json_response_returned_as_string(self):
        tool = HttpRequestTool()
        mock_resp = MagicMock()
        mock_resp.content = b"plain text response"
        mock_resp.status_code = 200
        mock_resp.headers = {}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await tool.execute({"url": "https://example.com"})

        assert result["body"] == "plain text response"

    @pytest.mark.asyncio
    async def test_request_error_raises_tool_execution_error(self):
        import httpx
        tool = HttpRequestTool()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.ConnectError("connection refused")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with pytest.raises(ToolExecutionError):
                await tool.execute({"url": "https://unreachable.example"})


# ── RestApiTool ───────────────────────────────────────────────────────────────

class TestRestApiTool:
    @pytest.mark.asyncio
    async def test_get_with_path(self):
        tool = RestApiTool()
        mock_resp = MagicMock()
        mock_resp.content = b'[{"id": 1}]'
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await tool.execute({"base_url": "https://api.example.com", "path": "users"})

        assert result["ok"] is True
        assert result["data"] == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_4xx_response_ok_false(self):
        tool = RestApiTool()
        mock_resp = MagicMock()
        mock_resp.content = b'{"error": "not found"}'
        mock_resp.status_code = 404

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await tool.execute({"base_url": "https://api.example.com", "path": "missing"})

        assert result["ok"] is False
        assert result["status_code"] == 404


# ── GraphqlTool ───────────────────────────────────────────────────────────────

class TestGraphqlTool:
    @pytest.mark.asyncio
    async def test_query_success(self):
        tool = GraphqlTool()
        mock_resp = MagicMock()
        mock_resp.content = json.dumps({"data": {"user": {"id": "1", "name": "Alice"}}}).encode()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await tool.execute({
                "endpoint": "https://api.example.com/graphql",
                "query": "{ user(id: 1) { id name } }",
            })

        assert result["ok"] is True
        assert result["data"] == {"user": {"id": "1", "name": "Alice"}}
        assert result["errors"] is None

    @pytest.mark.asyncio
    async def test_graphql_errors_ok_false(self):
        tool = GraphqlTool()
        mock_resp = MagicMock()
        mock_resp.content = json.dumps({"errors": [{"message": "field not found"}]}).encode()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await tool.execute({
                "endpoint": "https://api.example.com/graphql",
                "query": "{ badField }",
            })

        assert result["ok"] is False


# ── WebhookTool ───────────────────────────────────────────────────────────────

class TestWebhookTool:
    @pytest.mark.asyncio
    async def test_delivery_success(self):
        tool = WebhookTool()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await tool.execute({"url": "https://hooks.example.com/abc", "payload": {"event": "push"}})

        assert result["delivered"] is True
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_delivery_failed_non_2xx(self):
        tool = WebhookTool()
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await tool.execute({"url": "https://hooks.example.com/abc", "payload": {}})

        assert result["delivered"] is False

    @pytest.mark.asyncio
    async def test_hmac_signature_added(self):
        tool = WebhookTool()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await tool.execute({"url": "https://hooks.example.com/xyz", "payload": {"a": 1}, "secret": "mysecret"})

        _, call_kwargs = mock_client.post.call_args
        headers = call_kwargs.get("headers", {})
        assert "X-Webhook-Signature" in headers
        assert headers["X-Webhook-Signature"].startswith("sha256=")
