"""PR2-B: _drafter_node 후처리 — 보유 connection 자동 바인딩 (_autobind_connections)."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_schemas import NodeInstance, Position, WorkflowSchema
from common_schemas.enums import RiskLevel
from common_schemas.workflow import NodeConfig

from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
from ai_agent.domain.ports.connection_resolver import ConnectionResolver
from ai_agent.domain.ports.node_registry import NodeRegistry
from ai_agent.domain.ports.workflow_repository import WorkflowRepository
from ai_agent.domain.services import (
    DrafterService,
    IntentAnalyzerService,
    QAEvaluatorService,
    SlotFillingService,
)


def _node_config(node_id, node_type="gmail_send", required_connections=None) -> NodeConfig:
    return NodeConfig(
        node_id=node_id,
        node_type=node_type,
        name=node_type,
        category="action",
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=required_connections or [],
        description="",
        is_mvp=True,
    )


def _workflow(nodes) -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="WF",
        scope="private",
        is_draft=True,
        owner_user_id=uuid4(),
        nodes=nodes,
        connections=[],
    )


def _build(connection_resolver=None) -> LangGraphOrchestrator:
    from nodes_graph.domain.services.graph_validator import GraphValidator

    node_registry = AsyncMock(spec=NodeRegistry)
    node_registry.search = AsyncMock(return_value=[])
    return LangGraphOrchestrator(
        intent_analyzer=AsyncMock(spec=IntentAnalyzerService),
        drafter=AsyncMock(spec=DrafterService),
        qa_evaluator=AsyncMock(spec=QAEvaluatorService),
        slot_filler=SlotFillingService(),
        node_registry=node_registry,
        workflow_repo=AsyncMock(spec=WorkflowRepository),
        graph_validator=AsyncMock(spec=GraphValidator),
        connection_resolver=connection_resolver,
    )


@pytest.mark.asyncio
async def test_noop_when_resolver_not_injected():
    nid = uuid4()
    wf = _workflow([NodeInstance(instance_id=uuid4(), node_id=nid, parameters={}, position=Position(x=0, y=0))])
    orch = _build(connection_resolver=None)
    out, bound = await orch._autobind_connections(wf, [_node_config(nid, required_connections=["google"])], uuid4())
    assert bound == set()
    assert out.nodes[0].credential_id is None


@pytest.mark.asyncio
async def test_binds_credential_for_held_connection():
    nid = uuid4()
    cred = uuid4()
    resolver = AsyncMock(spec=ConnectionResolver)
    resolver.resolve = AsyncMock(return_value=cred)
    wf = _workflow([NodeInstance(instance_id=uuid4(), node_id=nid, parameters={}, position=Position(x=0, y=0))])
    orch = _build(connection_resolver=resolver)

    out, bound = await orch._autobind_connections(wf, [_node_config(nid, required_connections=["google"])], uuid4())

    assert bound == {"google"}
    # provider별 credential_ids에 기록 — validator(provider-aware)·executor가 소비 (REQ-012)
    assert out.nodes[0].credential_ids == {"google": cred}
    assert out.nodes[0].credential_id is None
    resolver.resolve.assert_awaited_once()


@pytest.mark.asyncio
async def test_binds_all_required_providers_for_multi_connection_node():
    """멀티커넥션 노드(required ≥2)는 보유한 provider 전부를 credential_ids에 채운다."""
    nid = uuid4()
    slack_cred, google_cred = uuid4(), uuid4()
    resolver = AsyncMock(spec=ConnectionResolver)
    resolver.resolve = AsyncMock(side_effect=lambda _uid, svc: {"slack": slack_cred, "google": google_cred}[svc])
    wf = _workflow([NodeInstance(instance_id=uuid4(), node_id=nid, parameters={}, position=Position(x=0, y=0))])
    orch = _build(connection_resolver=resolver)

    out, bound = await orch._autobind_connections(
        wf, [_node_config(nid, required_connections=["slack", "google"])], uuid4()
    )

    assert bound == {"slack", "google"}
    assert out.nodes[0].credential_ids == {"slack": slack_cred, "google": google_cred}


@pytest.mark.asyncio
async def test_multi_connection_partial_hold_binds_only_available():
    """보유한 provider만 바인딩 — 미보유(anthropic)는 credential_ids에서 제외."""
    nid = uuid4()
    google_cred = uuid4()
    resolver = AsyncMock(spec=ConnectionResolver)
    resolver.resolve = AsyncMock(side_effect=lambda _uid, svc: google_cred if svc == "google" else None)
    wf = _workflow([NodeInstance(instance_id=uuid4(), node_id=nid, parameters={}, position=Position(x=0, y=0))])
    orch = _build(connection_resolver=resolver)

    out, bound = await orch._autobind_connections(
        wf, [_node_config(nid, required_connections=["google", "anthropic"])], uuid4()
    )

    assert bound == {"google"}
    assert out.nodes[0].credential_ids == {"google": google_cred}


@pytest.mark.asyncio
async def test_preserves_existing_credential_id():
    nid = uuid4()
    existing = uuid4()
    resolver = AsyncMock(spec=ConnectionResolver)
    resolver.resolve = AsyncMock(return_value=uuid4())
    wf = _workflow([
        NodeInstance(
            instance_id=uuid4(), node_id=nid, parameters={},
            credential_id=existing, position=Position(x=0, y=0),
        )
    ])
    orch = _build(connection_resolver=resolver)

    out, bound = await orch._autobind_connections(wf, [_node_config(nid, required_connections=["google"])], uuid4())

    assert bound == set()
    assert out.nodes[0].credential_id == existing
    resolver.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_unresolved_provider_left_unbound():
    """api_key provider(anthropic)처럼 보유 connection이 없으면 바인딩 생략."""
    nid = uuid4()
    resolver = AsyncMock(spec=ConnectionResolver)
    resolver.resolve = AsyncMock(return_value=None)
    wf = _workflow([NodeInstance(instance_id=uuid4(), node_id=nid, parameters={}, position=Position(x=0, y=0))])
    orch = _build(connection_resolver=resolver)

    out, bound = await orch._autobind_connections(wf, [_node_config(nid, required_connections=["anthropic"])], uuid4())

    assert bound == set()
    assert out.nodes[0].credential_ids == {}
    assert out.nodes[0].credential_id is None
