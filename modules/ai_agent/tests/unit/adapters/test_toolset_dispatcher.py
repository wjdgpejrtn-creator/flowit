"""ToolsetDispatcher 단위 테스트 — ExecuteToolUseCase mock 주입 후 dispatch() 위임 확인."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ai_agent.adapters.tools.toolset_dispatcher import ToolsetDispatcher
from common_schemas.security import PermissionSource


@pytest.fixture
def mock_use_case():
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=MagicMock(data={"result": "ok"}))
    return uc


@pytest.fixture
def dispatcher(mock_use_case):
    return ToolsetDispatcher(mock_use_case)


@pytest.fixture
def context():
    return PermissionSource(
        user_id=uuid4(),
        role="User",
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",
    )


@pytest.mark.asyncio
async def test_dispatch_delegates_to_use_case(dispatcher, mock_use_case, context):
    """dispatch()가 ExecuteToolUseCase.execute()에 인자를 그대로 위임하는지 확인."""
    result = await dispatcher.dispatch(
        tool_name="rest_api",
        input_data={"url": "https://example.com"},
        context=context,
    )

    mock_use_case.execute.assert_awaited_once_with(
        tool_name="rest_api",
        input_data={"url": "https://example.com"},
        context=context,
        credential_id=None,
        node_id=None,
    )
    assert result.data == {"result": "ok"}


@pytest.mark.asyncio
async def test_dispatch_with_credential(dispatcher, mock_use_case, context):
    """credential_id, node_id가 있을 때 use_case에 그대로 전달하는지 확인."""
    cred_id = uuid4()
    node_id = uuid4()

    await dispatcher.dispatch(
        tool_name="slack_notify",
        input_data={"message": "hello"},
        context=context,
        credential_id=cred_id,
        node_id=node_id,
    )

    mock_use_case.execute.assert_awaited_once_with(
        tool_name="slack_notify",
        input_data={"message": "hello"},
        context=context,
        credential_id=cred_id,
        node_id=node_id,
    )
