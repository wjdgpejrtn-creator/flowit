"""Test that all 16 SQL schema files execute without errors."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))


@pytest.mark.asyncio
async def test_all_schemas_execute(db_engine):
    """Run all schema files in order and verify no SQL errors."""
    from src.helpers.migration_runner import MigrationRunner

    runner = MigrationRunner(db_engine)
    applied = await runner.run_schemas()
    assert len(applied) == 16, f"Expected 16 schemas, got {len(applied)}"


@pytest.mark.asyncio
async def test_tables_created(db_engine):
    """Verify expected tables exist after schema application."""
    from sqlalchemy import text

    expected_tables = {
        "users", "departments", "workflows", "executions",
        "credentials", "agents", "webhook_registry",
        "node_logs", "approvals", "notifications",
        "skills", "skill_stats", "skill_promotion_logs",
        "documents", "document_chunks",
        "checkpoints", "checkpoint_writes",
        "oauth_connections", "security_logs",
        "node_definitions", "intent_logs", "workflow_feedback",
        "sessions", "chat_messages",
        "agent_memories", "skill_reviews",
        "marketplace_recommendations", "skill_dependencies",
        "audit_logs",
        "node_results", "tool_executions",
        "storage_objects", "quality_gate_logs",
    }

    async with db_engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        actual_tables = {row[0] for row in result.fetchall()}

    missing = expected_tables - actual_tables
    assert not missing, f"Missing tables: {missing}"
