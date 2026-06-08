from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from auth.application.use_cases.list_connection_audit_use_case import ListConnectionAuditUseCase
from auth.domain.value_objects.connection_audit_entry import ConnectionAuditEntry
from common_schemas import PermissionSource
from common_schemas.exceptions import AuthorizationError


def _actor(role: str) -> PermissionSource:
    return PermissionSource(
        user_id=uuid4(),
        role=role,
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )


def _entry() -> ConnectionAuditEntry:
    return ConnectionAuditEntry(
        oauth_id=uuid4(),
        user_id=uuid4(),
        owner_email="dev@example.com",
        owner_name="Dev",
        owner_department="마케팅",
        service="google",
        account_id="sub-123",
        display_name="dev@example.com",
        scopes=["openid", "email"],
        is_active=True,
        connected_at=datetime.now(UTC),
    )


class _SpyOAuthRepo:
    def __init__(self, entries: list[ConnectionAuditEntry]) -> None:
        self._entries = entries
        self.calls: list[tuple[int, int]] = []

    async def list_connection_audit(self, limit: int = 200, offset: int = 0):
        self.calls.append((limit, offset))
        return self._entries


@pytest.mark.asyncio
async def test_admin_lists_all_connections():
    entries = [_entry(), _entry()]
    repo = _SpyOAuthRepo(entries)

    result = await ListConnectionAuditUseCase(repo).execute(actor=_actor("Admin"))

    assert result == entries
    assert repo.calls == [(200, 0)]  # 기본 limit/offset 전달


@pytest.mark.asyncio
async def test_admin_passes_pagination():
    repo = _SpyOAuthRepo([])

    await ListConnectionAuditUseCase(repo).execute(actor=_actor("Admin"), limit=50, offset=100)

    assert repo.calls == [(50, 100)]


@pytest.mark.asyncio
async def test_non_admin_rejected_without_query():
    repo = _SpyOAuthRepo([_entry()])

    for actor_role in ("User", "team_manager", "company_manager"):
        with pytest.raises(AuthorizationError):
            await ListConnectionAuditUseCase(repo).execute(actor=_actor(actor_role))

    assert repo.calls == []  # fail-closed — 인가 실패 시 repo 미조회
