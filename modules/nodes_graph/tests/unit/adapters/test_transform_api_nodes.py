"""transform 3종 + api 3종 외부 노드 process() unit test (ADR-0018 Phase 3a).

- transform: json_transform / data_mapping / text_template — 순수 로직, mock 불필요
- api: rest_api / graphql / webhook — httpx.AsyncClient를 fake로 치환해 검증

REQ-005 toolset BaseTool 로직을 BaseNode.process()로 포팅한 것이라, 입력 검증·
출력 형태는 toolset 구현과 동치여야 한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import httpx
import pytest
from common_schemas import NodeContext
from common_schemas.exceptions import ExecutionError, ValidationError

from nodes_graph.adapters.catalog.external._url_guard import validate_outbound_url
from nodes_graph.adapters.catalog.external.data_mapping import DataMappingInput, DataMappingNode
from nodes_graph.adapters.catalog.external.graphql import GraphqlInput, GraphqlNode
from nodes_graph.adapters.catalog.external.json_transform import JsonTransformInput, JsonTransformNode
from nodes_graph.adapters.catalog.external.rest_api import RestApiInput, RestApiNode
from nodes_graph.adapters.catalog.external.text_template import TextTemplateInput, TextTemplateNode
from nodes_graph.adapters.catalog.external.webhook import WebhookInput, WebhookNode

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())
# 공인 IP 리터럴 — SSRF 가드의 getaddrinfo가 네트워크 없이 즉시 public으로 분류한다.
_PUBLIC = "http://93.184.216.34"


# ----------------------------------------------------------------------
# transform — json_transform
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_json_transform_nested_and_wildcard():
    node = JsonTransformNode()
    nested = await node.process(
        JsonTransformInput(data={"user": {"name": "아름"}}, expression="user.name"), NODE_CTX
    )
    assert nested.result == "아름"
    assert nested.matched is True

    wildcard = await node.process(
        JsonTransformInput(data={"items": [{"name": "a"}, {"name": "b"}]}, expression="items[*].name"),
        NODE_CTX,
    )
    assert wildcard.result == ["a", "b"]


@pytest.mark.asyncio
async def test_json_transform_no_match_sets_matched_false():
    out = await JsonTransformNode().process(
        JsonTransformInput(data={"a": 1}, expression="missing"), NODE_CTX
    )
    assert out.result is None
    assert out.matched is False


@pytest.mark.asyncio
async def test_json_transform_empty_expression_raises():
    with pytest.raises(ValidationError, match="must not be empty"):
        await JsonTransformNode().process(
            JsonTransformInput(data={"a": 1}, expression="   "), NODE_CTX
        )


@pytest.mark.asyncio
async def test_json_transform_invalid_expression_raises():
    with pytest.raises(ValidationError, match="Invalid JMESPath"):
        await JsonTransformNode().process(
            JsonTransformInput(data={"a": 1}, expression="a]["), NODE_CTX
        )


# ----------------------------------------------------------------------
# transform — data_mapping
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_data_mapping_renames_and_keeps_unmapped():
    out = await DataMappingNode().process(
        DataMappingInput(data={"old": 1, "keep": 2}, mapping={"old": "new"}), NODE_CTX
    )
    assert out.result == {"new": 1, "keep": 2}
    assert out.mapped_count == 1


@pytest.mark.asyncio
async def test_data_mapping_drop_unmapped():
    out = await DataMappingNode().process(
        DataMappingInput(data={"old": 1, "drop": 2}, mapping={"old": "new"}, drop_unmapped=True),
        NODE_CTX,
    )
    assert out.result == {"new": 1}
    assert out.mapped_count == 1


@pytest.mark.asyncio
async def test_data_mapping_non_dict_data_raises():
    with pytest.raises(ValidationError, match="must be a JSON object"):
        await DataMappingNode().process(
            DataMappingInput(data=["not", "a", "dict"], mapping={}), NODE_CTX
        )


# ----------------------------------------------------------------------
# transform — text_template
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_template_renders():
    out = await TextTemplateNode().process(
        TextTemplateInput(template="안녕 {name}, {count}건", variables={"name": "아름", "count": 3}),
        NODE_CTX,
    )
    assert out.rendered == "안녕 아름, 3건"


@pytest.mark.asyncio
async def test_text_template_missing_variable_raises():
    with pytest.raises(ValidationError, match="missing"):
        await TextTemplateNode().process(
            TextTemplateInput(template="{a} {b}", variables={"a": 1}), NODE_CTX
        )


# ----------------------------------------------------------------------
# api — httpx fake
# ----------------------------------------------------------------------


@dataclass
class _FakeResponse:
    status_code: int
    content: bytes

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


class _HttpController:
    def __init__(self) -> None:
        self.response = _FakeResponse(200, b"{}")
        self.request: dict | None = None
        self.client_kwargs: dict | None = None


class _FakeClient:
    def __init__(self, ctrl: _HttpController, **kwargs) -> None:
        self._ctrl = ctrl
        ctrl.client_kwargs = kwargs

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def request(self, **kwargs):
        self._ctrl.request = kwargs
        return self._ctrl.response

    async def post(self, url, **kwargs):
        self._ctrl.request = {"url": url, **kwargs}
        return self._ctrl.response


@pytest.fixture
def fake_http(monkeypatch):
    ctrl = _HttpController()
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _FakeClient(ctrl, **kw))
    return ctrl


# ----------------------------------------------------------------------
# api — rest_api
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rest_api_success_builds_url_and_parses_json(fake_http):
    fake_http.response = _FakeResponse(200, b'{"id": 7}')
    out = await RestApiNode().process(
        RestApiInput(base_url=f"{_PUBLIC}/", path="/users", method="post"), NODE_CTX
    )
    assert out.status_code == 200
    assert out.data == {"id": 7}
    assert out.ok is True
    assert fake_http.request["url"] == f"{_PUBLIC}/users"
    assert fake_http.request["method"] == "POST"


@pytest.mark.asyncio
async def test_rest_api_non_json_falls_back_to_text(fake_http):
    fake_http.response = _FakeResponse(503, b"service unavailable")
    out = await RestApiNode().process(RestApiInput(base_url=_PUBLIC), NODE_CTX)
    assert out.data == "service unavailable"
    assert out.ok is False


# ----------------------------------------------------------------------
# api — graphql
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graphql_success_extracts_data(fake_http):
    fake_http.response = _FakeResponse(200, '{"data": {"viewer": "아름"}}'.encode())
    out = await GraphqlNode().process(
        GraphqlInput(endpoint=_PUBLIC, query="{ viewer }"), NODE_CTX
    )
    assert out.data == {"viewer": "아름"}
    assert out.errors == []
    assert out.ok is True


@pytest.mark.asyncio
async def test_graphql_errors_set_ok_false(fake_http):
    fake_http.response = _FakeResponse(200, b'{"data": null, "errors": [{"message": "bad"}]}')
    out = await GraphqlNode().process(
        GraphqlInput(endpoint=_PUBLIC, query="{ bad }"), NODE_CTX
    )
    assert out.errors == [{"message": "bad"}]
    assert out.ok is False


@pytest.mark.asyncio
async def test_graphql_non_json_raises(fake_http):
    fake_http.response = _FakeResponse(200, b"<html>not json</html>")
    with pytest.raises(ExecutionError, match="not valid JSON"):
        await GraphqlNode().process(
            GraphqlInput(endpoint=_PUBLIC, query="{ x }"), NODE_CTX
        )


# ----------------------------------------------------------------------
# api — webhook
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_delivered(fake_http):
    fake_http.response = _FakeResponse(204, b"")
    out = await WebhookNode().process(
        WebhookInput(url=_PUBLIC, payload={"event": "push"}), NODE_CTX
    )
    assert out.status_code == 204
    assert out.delivered is True


@pytest.mark.asyncio
async def test_webhook_non_2xx_not_delivered(fake_http):
    fake_http.response = _FakeResponse(500, b"")
    out = await WebhookNode().process(
        WebhookInput(url=_PUBLIC, payload={}), NODE_CTX
    )
    assert out.delivered is False


@pytest.mark.asyncio
async def test_webhook_secret_adds_hmac_signature(fake_http):
    fake_http.response = _FakeResponse(200, b"")
    await WebhookNode().process(
        WebhookInput(url=_PUBLIC, payload={"a": 1}, secret="topsecret"), NODE_CTX
    )
    signature = fake_http.request["headers"]["X-Webhook-Signature"]
    assert signature.startswith("sha256=")


# ----------------------------------------------------------------------
# api — connection_token 주입 + timeout 상한 (PR #115 리뷰 반영)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rest_api_injects_connection_token_as_bearer(fake_http):
    ctx = NodeContext(execution_id=uuid4(), user_id=uuid4(), connection_token="tok-xyz")
    await RestApiNode().process(RestApiInput(base_url=_PUBLIC), ctx)
    assert fake_http.request["headers"]["Authorization"] == "Bearer tok-xyz"


@pytest.mark.asyncio
async def test_rest_api_keeps_explicit_authorization_header(fake_http):
    """작성자가 명시한 Authorization 헤더는 connection_token이 덮어쓰지 않는다."""
    ctx = NodeContext(execution_id=uuid4(), user_id=uuid4(), connection_token="tok-xyz")
    await RestApiNode().process(
        RestApiInput(base_url=_PUBLIC, headers={"Authorization": "Basic abc"}), ctx
    )
    assert fake_http.request["headers"]["Authorization"] == "Basic abc"


@pytest.mark.asyncio
async def test_webhook_injects_connection_token_as_bearer(fake_http):
    ctx = NodeContext(execution_id=uuid4(), user_id=uuid4(), connection_token="tok-hook")
    await WebhookNode().process(WebhookInput(url=_PUBLIC, payload={}), ctx)
    assert fake_http.request["headers"]["Authorization"] == "Bearer tok-hook"


@pytest.mark.asyncio
async def test_rest_api_clamps_timeout_to_max(fake_http):
    await RestApiNode().process(RestApiInput(base_url=_PUBLIC, timeout_seconds=99999), NODE_CTX)
    assert fake_http.client_kwargs["timeout"] == 300


@pytest.mark.asyncio
async def test_webhook_clamps_timeout_to_max(fake_http):
    await WebhookNode().process(
        WebhookInput(url=_PUBLIC, payload={}, timeout_seconds=99999), NODE_CTX
    )
    assert fake_http.client_kwargs["timeout"] == 60


# ----------------------------------------------------------------------
# SSRF 가드 — validate_outbound_url
# ----------------------------------------------------------------------


class TestUrlGuard:
    @pytest.mark.asyncio
    async def test_allows_public_ip(self):
        await validate_outbound_url("http://93.184.216.34/path")  # raise 없음

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",  # GCP/AWS metadata
            "http://10.1.2.3/internal",                  # private
            "http://127.0.0.1:6379/",                    # loopback
            "http://192.168.0.1/",                       # private
        ],
    )
    async def test_blocks_internal_addresses(self, url):
        with pytest.raises(ValidationError, match="SSRF"):
            await validate_outbound_url(url)

    @pytest.mark.asyncio
    async def test_rejects_non_http_scheme(self):
        with pytest.raises(ValidationError, match="scheme"):
            await validate_outbound_url("ftp://93.184.216.34/")

    @pytest.mark.asyncio
    async def test_node_blocks_metadata_url_before_http_call(self, fake_http):
        """노드 경유 — SSRF URL은 httpx 호출 전에 차단된다."""
        with pytest.raises(ValidationError, match="SSRF"):
            await RestApiNode().process(
                RestApiInput(base_url="http://169.254.169.254", path="/token"), NODE_CTX
            )
        assert fake_http.request is None  # httpx 미호출
