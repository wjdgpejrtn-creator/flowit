from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas import NodeContext

from nodes_graph.application.catalog_registry import get_all_node_definitions
from nodes_graph.domain.catalog.trigger.api_poll_trigger import ApiPollTriggerInput, ApiPollTriggerNode
from nodes_graph.domain.catalog.trigger.manual_trigger import ManualTriggerInput, ManualTriggerNode
from nodes_graph.domain.catalog.trigger.schedule_trigger import ScheduleTriggerInput, ScheduleTriggerNode
from nodes_graph.domain.catalog.trigger.webhook_trigger import WebhookTriggerInput, WebhookTriggerNode

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())


def test_catalog_count():
    defs = get_all_node_definitions()
    # 28 domain (data 14 + control 8 + trigger 6) + 25 external = 53
    #   external 25 = 기존 14 + REQ-005 toolset 연동 신규 11 (박아름 5/19 toolset 정리 PR)
    #
    #   기존 14 (박아름 1주차 + gemma_chat PR #68):
    #   - 기타 2: http_request, pdf_generate
    #   - Communication 2: slack_post_message, gmail_send (Microsoft 보류)
    #   - Document 3: google_drive_read, google_sheets_read, google_docs_write (OneDrive 보류)
    #   - Data 3: postgresql_query, mysql_query, bigquery_query
    #   - AI/ML 2: anthropic_chat (OpenAI 보류), gemma_chat (5/14 야간 추가, PR #68)
    #   - Productivity 2: google_calendar_create_event, linear_create_issue (Notion 보류)
    #
    #   신규 11 (REQ-005 toolset 연동, 5/15 햄햄 합의 + 5/19 조장 안):
    #   - integration 2: rest_api, graphql
    #   - action 3: webhook, email_send, slack_notify
    #   - transform 4: text_template, json_transform, data_mapping, file_transform
    #   - utility 2: file_read, file_write
    #
    #   중복 제거 3종: http_request_tool(=external/http_request), conditional(=domain/control/if_condition),
    #                  loop(=domain/control/loop_list) → 양쪽 제거
    assert len(defs) == 53


def test_catalog_unique_node_ids():
    defs = get_all_node_definitions()
    ids = [d.node_id for d in defs]
    assert len(ids) == len(set(ids)), "node_id 중복 존재"


def test_catalog_unique_node_types():
    defs = get_all_node_definitions()
    types = [d.node_type for d in defs]
    assert len(types) == len(set(types)), "node_type 중복 존재"


def test_catalog_all_have_required_fields():
    for d in get_all_node_definitions():
        assert d.node_type
        assert d.name
        assert d.category
        assert d.version
        assert d.description
        assert isinstance(d.required_connections, list)


@pytest.mark.asyncio
async def test_schedule_trigger_passthrough():
    node = ScheduleTriggerNode()
    out = await node.process(ScheduleTriggerInput(cron="0 9 * * 1-5", triggered_at="2026-05-08T09:00:00Z"), NODE_CTX)
    assert out.cron == "0 9 * * 1-5"
    assert out.triggered_at == "2026-05-08T09:00:00Z"


@pytest.mark.asyncio
async def test_webhook_trigger_passthrough():
    node = WebhookTriggerNode()
    out = await node.process(WebhookTriggerInput(payload={"event": "push"}, method="POST"), NODE_CTX)
    assert out.payload == {"event": "push"}
    assert out.method == "POST"


@pytest.mark.asyncio
async def test_manual_trigger_passthrough():
    node = ManualTriggerNode()
    out = await node.process(ManualTriggerInput(payload={"key": "val"}, triggered_by="아름"), NODE_CTX)
    assert out.triggered_by == "아름"


@pytest.mark.asyncio
async def test_api_poll_trigger_diff():
    node = ApiPollTriggerNode()
    out = await node.process(ApiPollTriggerInput(
        response={"status": "active", "count": 5},
        previous_response={"status": "active", "count": 3},
    ), NODE_CTX)
    assert out.changed is True
    assert "count" in out.diff_keys


@pytest.mark.asyncio
async def test_api_poll_trigger_no_diff():
    node = ApiPollTriggerNode()
    out = await node.process(ApiPollTriggerInput(
        response={"status": "active"},
        previous_response={"status": "active"},
    ), NODE_CTX)
    assert out.changed is False
    assert out.diff_keys == []
