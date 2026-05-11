from __future__ import annotations

import pytest

from nodes_graph.application.catalog_registry import get_all_node_definitions
from nodes_graph.domain.catalog.trigger.api_poll_trigger import ApiPollTriggerInput, ApiPollTriggerNode
from nodes_graph.domain.catalog.trigger.manual_trigger import ManualTriggerInput, ManualTriggerNode
from nodes_graph.domain.catalog.trigger.schedule_trigger import ScheduleTriggerInput, ScheduleTriggerNode
from nodes_graph.domain.catalog.trigger.webhook_trigger import WebhookTriggerInput, WebhookTriggerNode


def test_catalog_count():
    defs = get_all_node_definitions()
    # 28 domain (data 14 + control 8 + trigger 6) + 10 external:
    #   - 기타 2: http_request, pdf_generate
    #   - Communication 4: slack_post_message, gmail_send, outlook_send, teams_post_message
    #   - Document 4: google_drive_read, google_sheets_read, google_docs_write, onedrive_read
    assert len(defs) == 38


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
    out = await node.process(ScheduleTriggerInput(cron="0 9 * * 1-5", triggered_at="2026-05-08T09:00:00Z"))
    assert out.cron == "0 9 * * 1-5"
    assert out.triggered_at == "2026-05-08T09:00:00Z"


@pytest.mark.asyncio
async def test_webhook_trigger_passthrough():
    node = WebhookTriggerNode()
    out = await node.process(WebhookTriggerInput(payload={"event": "push"}, method="POST"))
    assert out.payload == {"event": "push"}
    assert out.method == "POST"


@pytest.mark.asyncio
async def test_manual_trigger_passthrough():
    node = ManualTriggerNode()
    out = await node.process(ManualTriggerInput(payload={"key": "val"}, triggered_by="아름"))
    assert out.triggered_by == "아름"


@pytest.mark.asyncio
async def test_api_poll_trigger_diff():
    node = ApiPollTriggerNode()
    out = await node.process(ApiPollTriggerInput(
        response={"status": "active", "count": 5},
        previous_response={"status": "active", "count": 3},
    ))
    assert out.changed is True
    assert "count" in out.diff_keys


@pytest.mark.asyncio
async def test_api_poll_trigger_no_diff():
    node = ApiPollTriggerNode()
    out = await node.process(ApiPollTriggerInput(
        response={"status": "active"},
        previous_response={"status": "active"},
    ))
    assert out.changed is False
    assert out.diff_keys == []
