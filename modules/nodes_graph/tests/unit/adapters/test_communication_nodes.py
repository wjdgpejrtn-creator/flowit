"""Communication 카테고리 외부 노드 unit test.

Sprint 3 1주차 박아름 작업: Slack/Gmail 2종 NodeDefinition + BaseNode.
Microsoft(Outlook/Teams)는 데모 후속 개발로 보류 — 5/11 조장 결정.
process()는 NotImplementedError stub (실제 호출은 toolset connector 경유).
category="action" (DB CHECK 영문 8종 매핑).
"""
from __future__ import annotations

import pytest
from common_schemas.enums import RiskLevel

from nodes_graph.adapters.catalog.external.gmail_send import (
    GmailSendInput,
    GmailSendNode,
    get_node_definition as gmail_send_def,
)
from nodes_graph.adapters.catalog.external.slack_post_message import (
    SlackPostMessageInput,
    SlackPostMessageNode,
    get_node_definition as slack_post_def,
)


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
async def test_slack_process_raises_not_implemented():
    node = SlackPostMessageNode()
    with pytest.raises(NotImplementedError, match="toolset connector"):
        await node.process(SlackPostMessageInput(channel="#general", text="hi"))


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
async def test_gmail_process_raises_not_implemented():
    node = GmailSendNode()
    with pytest.raises(NotImplementedError, match="toolset connector"):
        await node.process(GmailSendInput(to=["a@b.com"], subject="s", body="b"))


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
