"""Data + AI/ML + Productivity 카테고리 외부 노드 unit test.

Sprint 3 1주차 박아름 작업:
- Data 3종: PostgreSQL, MySQL, BigQuery (integration)
- AI/ML 1종: Anthropic (ai). OpenAI는 데모 후속 개발 보류 — 5/11 조장 결정
- Productivity 2종: Google Calendar, Linear (integration). Notion은 데모 후속 보류

process()는 NotImplementedError stub. category는 DB CHECK 영문 8종 매핑.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from nodes_graph.adapters.catalog.external.anthropic_chat import (
    AnthropicChatInput,
    AnthropicChatNode,
)
from nodes_graph.adapters.catalog.external.anthropic_chat import (
    get_node_definition as anthropic_chat_def,
)
from nodes_graph.adapters.catalog.external.bigquery_query import (
    BigqueryQueryInput,
    BigqueryQueryNode,
)
from nodes_graph.adapters.catalog.external.bigquery_query import (
    get_node_definition as bigquery_query_def,
)
from nodes_graph.adapters.catalog.external.google_calendar_create_event import (
    GoogleCalendarCreateEventInput,
    GoogleCalendarCreateEventNode,
)
from nodes_graph.adapters.catalog.external.google_calendar_create_event import (
    get_node_definition as gcal_create_def,
)
from nodes_graph.adapters.catalog.external.linear_create_issue import (
    LinearCreateIssueInput,
    LinearCreateIssueNode,
)
from nodes_graph.adapters.catalog.external.linear_create_issue import (
    get_node_definition as linear_create_def,
)
from nodes_graph.adapters.catalog.external.mysql_query import (
    MysqlQueryInput,
    MysqlQueryNode,
)
from nodes_graph.adapters.catalog.external.mysql_query import (
    get_node_definition as mysql_query_def,
)
from nodes_graph.adapters.catalog.external.postgresql_query import (
    PostgresqlQueryInput,
    PostgresqlQueryNode,
)
from nodes_graph.adapters.catalog.external.postgresql_query import (
    get_node_definition as postgresql_query_def,
)

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())


# ----------------------------------------------------------------------
# Data — PostgreSQL / MySQL / BigQuery
# ----------------------------------------------------------------------


def test_postgresql_query_definition_fields():
    d = postgresql_query_def()
    assert d.node_type == "postgresql_query"
    assert d.category == "integration"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["postgresql"]
    assert d.service_type == "postgresql"


@pytest.mark.asyncio
async def test_postgresql_query_process_requires_credential():
    """ADR-0018 Phase 3d 실구현 — credential(DSN) 없이 ValidationError.
    실행 경로 전체는 test_db_file_google_nodes.py 참조."""
    node = PostgresqlQueryNode()
    with pytest.raises(ValidationError, match="credential"):
        await node.process(PostgresqlQueryInput(query="SELECT 1"), NODE_CTX)


def test_mysql_query_definition_fields():
    d = mysql_query_def()
    assert d.node_type == "mysql_query"
    assert d.category == "integration"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["mysql"]
    assert d.service_type == "mysql"


@pytest.mark.asyncio
async def test_mysql_query_process_requires_credential():
    """ADR-0018 Phase 3d 실구현 — credential(연결 URL) 없이 ValidationError."""
    node = MysqlQueryNode()
    with pytest.raises(ValidationError, match="credential"):
        await node.process(MysqlQueryInput(query="SELECT 1"), NODE_CTX)


def test_bigquery_query_definition_fields():
    d = bigquery_query_def()
    assert d.node_type == "bigquery_query"
    assert d.category == "integration"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["google"]
    assert d.service_type == "google_workspace"


@pytest.mark.asyncio
async def test_bigquery_query_process_requires_credential():
    """ADR-0018 Phase 3d 실구현 — credential(Google OAuth 토큰) 없이 ValidationError."""
    node = BigqueryQueryNode()
    with pytest.raises(ValidationError, match="credential"):
        await node.process(BigqueryQueryInput(project_id="p", query="SELECT 1"), NODE_CTX)


# ----------------------------------------------------------------------
# AI/ML — Anthropic only (OpenAI 보류)
# ----------------------------------------------------------------------


def test_anthropic_chat_definition_fields():
    d = anthropic_chat_def()
    assert d.node_type == "anthropic_chat"
    assert d.category == "ai"
    assert d.risk_level == RiskLevel.MEDIUM
    assert d.required_connections == ["anthropic"]
    assert d.service_type == "anthropic"


@pytest.mark.asyncio
async def test_anthropic_chat_process_requires_credential():
    """anthropic_chat은 ADR-0018 Phase 3c 실구현 — credential(API key) 없이 ValidationError.
    실행 경로 전체는 test_llm_linear_nodes.py 참조."""
    node = AnthropicChatNode()
    with pytest.raises(ValidationError, match="credential"):
        await node.process(AnthropicChatInput(
            model="claude-opus-4-7",
            messages=[{"role": "user", "content": "hi"}],
        ), NODE_CTX)


# ----------------------------------------------------------------------
# Productivity — Google Calendar / Linear (Notion 보류)
# ----------------------------------------------------------------------


def test_google_calendar_create_event_definition_fields():
    d = gcal_create_def()
    assert d.node_type == "google_calendar_create_event"
    assert d.category == "integration"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["google"]
    assert d.service_type == "google_workspace"


@pytest.mark.asyncio
async def test_google_calendar_create_event_process_requires_credential():
    """ADR-0018 Phase 3d 실구현 — credential(Google OAuth 토큰) 없이 ValidationError."""
    node = GoogleCalendarCreateEventNode()
    with pytest.raises(ValidationError, match="credential"):
        await node.process(GoogleCalendarCreateEventInput(
            calendar_id="primary",
            summary="meeting",
            start="2026-05-11T09:00:00+09:00",
            end="2026-05-11T10:00:00+09:00",
        ), NODE_CTX)


def test_linear_create_issue_definition_fields():
    d = linear_create_def()
    assert d.node_type == "linear_create_issue"
    assert d.category == "integration"
    assert d.risk_level == RiskLevel.HIGH
    assert d.required_connections == ["linear"]
    assert d.service_type == "linear"


@pytest.mark.asyncio
async def test_linear_create_issue_process_requires_credential():
    """linear_create_issue는 ADR-0018 Phase 3c 실구현 — credential(API key) 없이 ValidationError.
    실행 경로 전체는 test_llm_linear_nodes.py 참조."""
    node = LinearCreateIssueNode()
    with pytest.raises(ValidationError, match="credential"):
        await node.process(LinearCreateIssueInput(team_id="t1", title="task"), NODE_CTX)


# ----------------------------------------------------------------------
# Cross-checks
# ----------------------------------------------------------------------


def test_all_six_nodes_have_unique_ids():
    ids = {
        postgresql_query_def().node_id, mysql_query_def().node_id, bigquery_query_def().node_id,
        anthropic_chat_def().node_id,
        gcal_create_def().node_id, linear_create_def().node_id,
    }
    assert len(ids) == 6


def test_db_nodes_share_risk_level_high():
    """SQL 쿼리 노드는 write 가능성 있어 일률 HIGH."""
    for d in (postgresql_query_def(), mysql_query_def(), bigquery_query_def()):
        assert d.risk_level == RiskLevel.HIGH


def test_llm_node_risk_level_medium():
    """LLM 호출은 외부 호출이지만 자체 시스템 변경 X — MEDIUM."""
    assert anthropic_chat_def().risk_level == RiskLevel.MEDIUM
