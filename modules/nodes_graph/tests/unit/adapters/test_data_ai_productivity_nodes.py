"""Data + AI/ML + Productivity 카테고리 외부 노드 8종 unit test.

5/14 plan §4.2 박아름 산출물:
- Data 3종: PostgreSQL, MySQL, BigQuery
- AI/ML 2종: OpenAI, Anthropic
- Productivity 3종: Notion, Google Calendar, Linear

process()는 Sprint 3 v1에서 NotImplementedError stub.
"""
from __future__ import annotations

import pytest
from common_schemas.enums import RiskLevel

from nodes_graph.adapters.catalog.external.anthropic_chat import (
    AnthropicChatInput,
    AnthropicChatNode,
    get_node_definition as anthropic_chat_def,
)
from nodes_graph.adapters.catalog.external.bigquery_query import (
    BigqueryQueryInput,
    BigqueryQueryNode,
    get_node_definition as bigquery_query_def,
)
from nodes_graph.adapters.catalog.external.google_calendar_create_event import (
    GoogleCalendarCreateEventInput,
    GoogleCalendarCreateEventNode,
    get_node_definition as gcal_create_def,
)
from nodes_graph.adapters.catalog.external.linear_create_issue import (
    LinearCreateIssueInput,
    LinearCreateIssueNode,
    get_node_definition as linear_create_def,
)
from nodes_graph.adapters.catalog.external.mysql_query import (
    MysqlQueryInput,
    MysqlQueryNode,
    get_node_definition as mysql_query_def,
)
from nodes_graph.adapters.catalog.external.notion_create_page import (
    NotionCreatePageInput,
    NotionCreatePageNode,
    get_node_definition as notion_create_def,
)
from nodes_graph.adapters.catalog.external.openai_chat import (
    OpenaiChatInput,
    OpenaiChatNode,
    get_node_definition as openai_chat_def,
)
from nodes_graph.adapters.catalog.external.postgresql_query import (
    PostgresqlQueryInput,
    PostgresqlQueryNode,
    get_node_definition as postgresql_query_def,
)


# ----------------------------------------------------------------------
# Data — PostgreSQL / MySQL / BigQuery
# ----------------------------------------------------------------------


def test_postgresql_query_definition_fields():
    d = postgresql_query_def()
    assert d.node_type == "postgresql_query"
    assert d.category == "데이터 소스"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["postgresql"]
    assert d.service_type == "postgresql"


@pytest.mark.asyncio
async def test_postgresql_query_process_raises_not_implemented():
    node = PostgresqlQueryNode()
    with pytest.raises(NotImplementedError, match="toolset connector"):
        await node.process(PostgresqlQueryInput(query="SELECT 1"))


def test_mysql_query_definition_fields():
    d = mysql_query_def()
    assert d.node_type == "mysql_query"
    assert d.category == "데이터 소스"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["mysql"]
    assert d.service_type == "mysql"


@pytest.mark.asyncio
async def test_mysql_query_process_raises_not_implemented():
    node = MysqlQueryNode()
    with pytest.raises(NotImplementedError):
        await node.process(MysqlQueryInput(query="SELECT 1"))


def test_bigquery_query_definition_fields():
    d = bigquery_query_def()
    assert d.node_type == "bigquery_query"
    assert d.category == "데이터 소스"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["google"]
    assert d.service_type == "google_workspace"


@pytest.mark.asyncio
async def test_bigquery_query_process_raises_not_implemented():
    node = BigqueryQueryNode()
    with pytest.raises(NotImplementedError):
        await node.process(BigqueryQueryInput(project_id="p", query="SELECT 1"))


# ----------------------------------------------------------------------
# AI/ML — OpenAI / Anthropic
# ----------------------------------------------------------------------


def test_openai_chat_definition_fields():
    d = openai_chat_def()
    assert d.node_type == "openai_chat"
    assert d.category == "AI / LLM"
    assert d.risk_level == RiskLevel.MEDIUM
    assert d.required_connections == ["openai"]
    assert d.service_type == "openai"


@pytest.mark.asyncio
async def test_openai_chat_process_raises_not_implemented():
    node = OpenaiChatNode()
    with pytest.raises(NotImplementedError):
        await node.process(OpenaiChatInput(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}]))


def test_anthropic_chat_definition_fields():
    d = anthropic_chat_def()
    assert d.node_type == "anthropic_chat"
    assert d.category == "AI / LLM"
    assert d.risk_level == RiskLevel.MEDIUM
    assert d.required_connections == ["anthropic"]
    assert d.service_type == "anthropic"


@pytest.mark.asyncio
async def test_anthropic_chat_process_raises_not_implemented():
    node = AnthropicChatNode()
    with pytest.raises(NotImplementedError):
        await node.process(AnthropicChatInput(
            model="claude-opus-4-7",
            messages=[{"role": "user", "content": "hi"}],
        ))


# ----------------------------------------------------------------------
# Productivity — Notion / Google Calendar / Linear
# ----------------------------------------------------------------------


def test_notion_create_page_definition_fields():
    d = notion_create_def()
    assert d.node_type == "notion_create_page"
    assert d.category == "외부 API 연동"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["notion"]
    assert d.service_type == "notion"


@pytest.mark.asyncio
async def test_notion_create_page_process_raises_not_implemented():
    node = NotionCreatePageNode()
    with pytest.raises(NotImplementedError):
        await node.process(NotionCreatePageInput(parent_id="db_id"))


def test_google_calendar_create_event_definition_fields():
    d = gcal_create_def()
    assert d.node_type == "google_calendar_create_event"
    assert d.category == "외부 API 연동"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["google"]
    assert d.service_type == "google_workspace"


@pytest.mark.asyncio
async def test_google_calendar_create_event_process_raises_not_implemented():
    node = GoogleCalendarCreateEventNode()
    with pytest.raises(NotImplementedError):
        await node.process(GoogleCalendarCreateEventInput(
            calendar_id="primary",
            summary="meeting",
            start="2026-05-11T09:00:00+09:00",
            end="2026-05-11T10:00:00+09:00",
        ))


def test_linear_create_issue_definition_fields():
    d = linear_create_def()
    assert d.node_type == "linear_create_issue"
    assert d.category == "외부 API 연동"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["linear"]
    assert d.service_type == "linear"


@pytest.mark.asyncio
async def test_linear_create_issue_process_raises_not_implemented():
    node = LinearCreateIssueNode()
    with pytest.raises(NotImplementedError):
        await node.process(LinearCreateIssueInput(team_id="t1", title="task"))


# ----------------------------------------------------------------------
# Cross-checks
# ----------------------------------------------------------------------


def test_all_eight_nodes_have_unique_ids():
    ids = {
        postgresql_query_def().node_id, mysql_query_def().node_id, bigquery_query_def().node_id,
        openai_chat_def().node_id, anthropic_chat_def().node_id,
        notion_create_def().node_id, gcal_create_def().node_id, linear_create_def().node_id,
    }
    assert len(ids) == 8


def test_db_nodes_share_risk_level_high():
    """SQL 쿼리 노드는 write 가능성 있어 일률 HIGH."""
    for d in (postgresql_query_def(), mysql_query_def(), bigquery_query_def()):
        assert d.risk_level == RiskLevel.HIGH


def test_llm_nodes_share_risk_level_medium():
    """LLM 호출은 외부 호출이지만 자체 시스템 변경 X — MEDIUM."""
    for d in (openai_chat_def(), anthropic_chat_def()):
        assert d.risk_level == RiskLevel.MEDIUM
