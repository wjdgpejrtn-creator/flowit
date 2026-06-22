"""Communication 카테고리 외부 노드 unit test.

Sprint 3 1주차 박아름 작업: Slack/Gmail 2종 NodeDefinition + BaseNode.
Microsoft(Outlook/Teams)는 데모 후속 개발로 보류 — 5/11 조장 결정.
process()는 NotImplementedError stub (실제 호출은 toolset connector 경유).
category="action" (DB CHECK 영문 8종 매핑).
"""
from __future__ import annotations

import base64
from email.mime.multipart import MIMEMultipart
from uuid import uuid4

import pytest
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from nodes_graph.adapters.catalog.external.gmail_send import (
    GmailSendInput,
    GmailSendNode,
)
from nodes_graph.adapters.catalog.external.gmail_send import (
    get_node_definition as gmail_send_def,
)
from nodes_graph.adapters.catalog.external.slack_post_message import (
    SlackPostMessageInput,
    SlackPostMessageNode,
)
from nodes_graph.adapters.catalog.external.slack_post_message import (
    get_node_definition as slack_post_def,
)

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())


# ----------------------------------------------------------------------
# Slack
# ----------------------------------------------------------------------


def test_slack_node_definition_fields():
    d = slack_post_def()
    assert d.node_type == "slack_post_message"
    assert d.name == "Slack 메시지 전송"
    assert d.category == "action"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["slack"]
    assert d.service_type == "slack"
    assert d.is_mvp is True


def test_slack_node_metadata_consistent_with_definition():
    node = SlackPostMessageNode()
    d = slack_post_def()
    assert node.metadata.node_id == d.node_id
    assert node.metadata.category == d.category
    assert node.metadata.risk_level == d.risk_level


@pytest.mark.asyncio
async def test_slack_process_requires_credential():
    """slack_post_message는 ADR-0018 Phase 3b에서 실구현 — credential(Bot 토큰)
    없이 호출하면 ValidationError. 실행 경로 전체는 test_messaging_nodes.py 참조."""
    node = SlackPostMessageNode()
    with pytest.raises(ValidationError, match="credential"):
        await node.process(SlackPostMessageInput(channel="#general", text="hi"), NODE_CTX)


# ----------------------------------------------------------------------
# Gmail
# ----------------------------------------------------------------------


def test_gmail_node_definition_fields():
    d = gmail_send_def()
    assert d.node_type == "gmail_send"
    assert d.name == "Gmail 메일 전송"
    assert d.category == "action"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["google"]
    assert d.service_type == "google_workspace"


@pytest.mark.asyncio
async def test_gmail_process_requires_credential():
    """gmail_send는 ADR-0018 Phase 3d 실구현 — credential(Google OAuth 토큰) 없이
    ValidationError. 실행 경로 전체는 test_db_file_google_nodes.py 참조."""
    node = GmailSendNode()
    with pytest.raises(ValidationError, match="credential"):
        await node.process(GmailSendInput(to=["a@b.com"], subject="s", body="b"), NODE_CTX)


# ----------------------------------------------------------------------
# Gmail 첨부 견고화 (_attach_file) — email_send와 동일 계약 (PR #537 이식)
# ----------------------------------------------------------------------


def _multipart() -> MIMEMultipart:
    return MIMEMultipart()


def test_gmail_attach_dict_valid():
    msg = _multipart()
    content = base64.b64encode(b"%PDF-1.4 fake").decode()
    GmailSendNode._attach_file(
        msg, {"filename": "report.pdf", "content_base64": content, "mimetype": "application/pdf"}
    )
    parts = msg.get_payload()
    assert len(parts) == 1
    assert parts[0].get_filename() == "report.pdf"
    assert parts[0].get_content_subtype() == "pdf"


def test_gmail_attach_bare_string_allowed():
    """LLM이 attachments=["${...}"]로 채워 런타임 해소 시 bare base64 문자열도 허용."""
    msg = _multipart()
    GmailSendNode._attach_file(msg, base64.b64encode(b"data").decode())
    parts = msg.get_payload()
    assert len(parts) == 1
    assert parts[0].get_filename() == "attachment"


def test_gmail_attach_missing_content_raises():
    msg = _multipart()
    with pytest.raises(ValidationError, match="content_base64가 없습니다"):
        GmailSendNode._attach_file(msg, {"filename": "x.pdf"})


def test_gmail_attach_invalid_base64_raises():
    msg = _multipart()
    with pytest.raises(ValidationError, match="유효한 base64가 아닙니다"):
        GmailSendNode._attach_file(msg, {"filename": "x.pdf", "content_base64": "/path/to/file.pdf"})


# ----------------------------------------------------------------------
# Cross-checks
# ----------------------------------------------------------------------


def test_all_communication_nodes_have_unique_ids():
    ids = {slack_post_def().node_id, gmail_send_def().node_id}
    assert len(ids) == 2


def test_all_communication_nodes_have_external_service_type():
    """OAuth 필요 외부 서비스 노드는 service_type이 비어있으면 안 됨 (REQ-002 H-4 합의)."""
    for d in (slack_post_def(), gmail_send_def()):
        assert d.service_type, f"{d.node_type}의 service_type 비어있음"
        assert d.required_connections, f"{d.node_type}의 required_connections 비어있음"
        assert d.risk_level == RiskLevel.HIGH, f"{d.node_type} 쓰기 작업이므로 risk_level=HIGH 기대"
        assert d.category == "action", f"{d.node_type} category=action 기대"
