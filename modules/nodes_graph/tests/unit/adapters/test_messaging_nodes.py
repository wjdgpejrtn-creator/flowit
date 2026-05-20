"""messaging 3종 외부 노드 process() unit test (ADR-0018 Phase 3b).

- email_send: smtplib을 fake로 치환
- slack_notify / slack_post_message: httpx.AsyncClient를 fake로 치환
- http_request: Phase 3b에서 추가된 SSRF 가드 검증

email_send / slack_notify는 REQ-005 toolset BaseTool 포팅, slack_post_message는
그린필드. slack 2종은 context.connection_token(웹훅 URL / Bot 토큰)을 소비한다.
"""
from __future__ import annotations

import smtplib
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
import pytest
from common_schemas import NodeContext
from common_schemas.exceptions import ValidationError

from nodes_graph.adapters.catalog.external.email_send import EmailSendInput, EmailSendNode
from nodes_graph.adapters.catalog.external.http_request import HttpRequestInput, HttpRequestNode
from nodes_graph.adapters.catalog.external.slack_notify import SlackNotifyInput, SlackNotifyNode
from nodes_graph.adapters.catalog.external.slack_post_message import (
    SlackPostMessageInput,
    SlackPostMessageNode,
)

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())
# 공인 IP 리터럴 — SSRF 가드의 getaddrinfo가 네트워크 없이 즉시 public으로 분류한다.
_PUBLIC = "http://93.184.216.34"


def _ctx_with_token(token: str) -> NodeContext:
    return NodeContext(execution_id=uuid4(), user_id=uuid4(), connection_token=token)


# ----------------------------------------------------------------------
# email_send — smtplib fake
# ----------------------------------------------------------------------


@pytest.fixture
def fake_smtp(monkeypatch):
    """smtplib.SMTP를 치환 — 발송 호출을 기록한 dict 리스트를 반환."""
    records: list[dict] = []

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None) -> None:
            self.record = {"host": host, "port": port, "tls": False, "login": None, "sendmail": None}
            records.append(self.record)

        def __enter__(self) -> _FakeSMTP:
            return self

        def __exit__(self, *exc) -> bool:
            return False

        def starttls(self, context=None) -> None:
            self.record["tls"] = True

        def login(self, user, password) -> None:
            self.record["login"] = (user, password)

        def sendmail(self, from_addr, to_addrs, message) -> None:
            self.record["sendmail"] = (from_addr, list(to_addrs))

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    return records


def _email_input(**overrides) -> EmailSendInput:
    base = dict(
        smtp_host="smtp.example.com",
        from_address="bot@example.com",
        to_addresses=["a@example.com", "b@example.com"],
        subject="제목",
        body="본문",
    )
    base.update(overrides)
    return EmailSendInput(**base)


@pytest.mark.asyncio
async def test_email_send_success_without_credential(fake_smtp):
    out = await EmailSendNode().process(_email_input(), NODE_CTX)
    assert out.sent is True
    assert out.recipients_count == 2
    assert fake_smtp[0]["sendmail"][1] == ["a@example.com", "b@example.com"]
    assert fake_smtp[0]["login"] is None  # credential 없으면 login 생략


@pytest.mark.asyncio
async def test_email_send_logs_in_with_credential(fake_smtp):
    await EmailSendNode().process(_email_input(), _ctx_with_token("smtpuser:smtppass"))
    assert fake_smtp[0]["login"] == ("smtpuser", "smtppass")


@pytest.mark.asyncio
async def test_email_send_bad_credential_format_raises(fake_smtp):
    with pytest.raises(ValidationError, match="username:password"):
        await EmailSendNode().process(_email_input(), _ctx_with_token("no-colon-token"))


@pytest.mark.asyncio
async def test_email_send_empty_recipients_raises(fake_smtp):
    with pytest.raises(ValidationError, match="recipient"):
        await EmailSendNode().process(_email_input(to_addresses=[]), NODE_CTX)


# ----------------------------------------------------------------------
# httpx fake — slack 2종
# ----------------------------------------------------------------------


@dataclass
class _FakeResponse:
    status_code: int
    json_body: Any = None

    def json(self) -> Any:
        return self.json_body


class _HttpController:
    def __init__(self) -> None:
        self.response = _FakeResponse(200, {"ok": True})
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
# slack_notify
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_notify_success(fake_http):
    fake_http.response = _FakeResponse(200)
    out = await SlackNotifyNode().process(
        SlackNotifyInput(message="배포 완료", channel="#ops"), _ctx_with_token(_PUBLIC)
    )
    assert out.sent is True
    assert out.status_code == 200
    assert fake_http.request["url"] == _PUBLIC
    assert fake_http.request["json"] == {"text": "배포 완료", "channel": "#ops"}


@pytest.mark.asyncio
async def test_slack_notify_missing_token_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await SlackNotifyNode().process(SlackNotifyInput(message="hi"), NODE_CTX)


@pytest.mark.asyncio
async def test_slack_notify_non_200_not_sent(fake_http):
    fake_http.response = _FakeResponse(500)
    out = await SlackNotifyNode().process(
        SlackNotifyInput(message="hi"), _ctx_with_token(_PUBLIC)
    )
    assert out.sent is False
    assert out.status_code == 500


@pytest.mark.asyncio
async def test_slack_notify_blocks_internal_webhook(fake_http):
    """credential로 주입된 웹훅 URL이 내부 주소면 SSRF 가드가 차단."""
    with pytest.raises(ValidationError, match="SSRF"):
        await SlackNotifyNode().process(
            SlackNotifyInput(message="hi"), _ctx_with_token("http://169.254.169.254/hook")
        )
    assert fake_http.request is None


# ----------------------------------------------------------------------
# slack_post_message
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_post_message_success(fake_http):
    fake_http.response = _FakeResponse(200, {"ok": True, "ts": "1717.0001", "channel": "C0001"})
    out = await SlackPostMessageNode().process(
        SlackPostMessageInput(channel="#general", text="안녕"), _ctx_with_token("xoxb-test")
    )
    assert out.ok is True
    assert out.ts == "1717.0001"
    assert out.channel == "C0001"
    assert fake_http.request["headers"]["Authorization"] == "Bearer xoxb-test"
    assert fake_http.request["json"]["channel"] == "#general"


@pytest.mark.asyncio
async def test_slack_post_message_logical_error_passthrough(fake_http):
    """Slack은 논리 오류도 HTTP 200 — ok=False + raw_response로 전달."""
    fake_http.response = _FakeResponse(200, {"ok": False, "error": "channel_not_found"})
    out = await SlackPostMessageNode().process(
        SlackPostMessageInput(channel="#nope", text="안녕"), _ctx_with_token("xoxb-test")
    )
    assert out.ok is False
    assert out.raw_response["error"] == "channel_not_found"
    assert out.ts == ""


@pytest.mark.asyncio
async def test_slack_post_message_missing_token_raises(fake_http):
    with pytest.raises(ValidationError, match="credential"):
        await SlackPostMessageNode().process(
            SlackPostMessageInput(channel="#general", text="안녕"), NODE_CTX
        )


# ----------------------------------------------------------------------
# http_request — SSRF 가드 후속 (PR #115 follow-up)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_request_blocks_internal_url(fake_http):
    with pytest.raises(ValidationError, match="SSRF"):
        await HttpRequestNode().process(
            HttpRequestInput(url="http://169.254.169.254/latest/meta-data/"), NODE_CTX
        )
    assert fake_http.request is None
