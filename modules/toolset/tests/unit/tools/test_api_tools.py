from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from toolset.adapters.internal.api.graphql_tool import GraphqlTool
from toolset.adapters.internal.api.rest_api_tool import RestApiTool
from toolset.adapters.internal.api.webhook_tool import WebhookTool
from toolset.domain.exceptions import ToolExecutionError


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
