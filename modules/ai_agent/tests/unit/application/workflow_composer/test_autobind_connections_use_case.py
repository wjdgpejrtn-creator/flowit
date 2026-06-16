"""AutobindConnectionsUseCase 단위 테스트 — 편집 경로 노드 선바인딩 (E_MISSING_CONNECTION 방지)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from common_schemas import NodeInstance, Position, WorkflowSchema

from ai_agent.application.agents.workflow_composer import AutobindConnectionsUseCase


class _FakeResolver:
    """ConnectionResolver 페이크 — (service) → credential_id 매핑."""

    def __init__(self, mapping: dict[str, UUID], raises: set[str] | None = None) -> None:
        self._mapping = mapping
        self._raises = raises or set()

    async def resolve(self, user_id: UUID, service: str) -> UUID | None:
        if service in self._raises:
            raise RuntimeError("oauth lookup boom")
        return self._mapping.get(service)


class _FakeNodeDefRepo:
    """NodeDefinitionRepository 페이크 — node_id → required_connections."""

    def __init__(self, required_by_node_id: dict[UUID, list[str]], missing: set[UUID] | None = None) -> None:
        self._required = required_by_node_id
        self._missing = missing or set()

    async def get_by_id(self, node_id: UUID):
        if node_id in self._missing:
            return None
        return SimpleNamespace(node_id=node_id, required_connections=self._required.get(node_id, []))


def _node(node_id: UUID, *, credential_id=None, credential_ids=None) -> NodeInstance:
    return NodeInstance(
        instance_id=uuid4(),
        node_id=node_id,
        parameters={},
        credential_id=credential_id,
        credential_ids=credential_ids or {},
        position=Position(x=0, y=0),
    )


def _wf(*nodes: NodeInstance) -> WorkflowSchema:
    return WorkflowSchema(
        workflow_id=uuid4(),
        name="wf",
        nodes=list(nodes),
        connections=[],
        scope="private",
        is_draft=False,
    )


@pytest.mark.asyncio
async def test_binds_unresolved_provider():
    node_id, user_id, cred = uuid4(), uuid4(), uuid4()
    wf = _wf(_node(node_id))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({"google": cred}),
        node_def_repo=_FakeNodeDefRepo({node_id: ["google"]}),
    )

    out = await uc.execute(wf, user_id)

    assert out.nodes[0].credential_ids == {"google": cred}


@pytest.mark.asyncio
async def test_preserves_existing_user_binding():
    node_id, user_id = uuid4(), uuid4()
    chosen = uuid4()  # 사용자가 명시 선택한 connection
    auto = uuid4()    # resolver가 줄 다른 connection
    wf = _wf(_node(node_id, credential_ids={"google": chosen}))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({"google": auto}),
        node_def_repo=_FakeNodeDefRepo({node_id: ["google"]}),
    )

    out = await uc.execute(wf, user_id)

    # 이미 바인딩된 provider는 덮어쓰지 않는다
    assert out.nodes[0].credential_ids == {"google": chosen}


@pytest.mark.asyncio
async def test_multi_provider_binds_only_missing():
    node_id, user_id = uuid4(), uuid4()
    slack_cred, google_cred = uuid4(), uuid4()
    wf = _wf(_node(node_id, credential_ids={"slack": slack_cred}))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({"google": google_cred, "slack": uuid4()}),
        node_def_repo=_FakeNodeDefRepo({node_id: ["slack", "google"]}),
    )

    out = await uc.execute(wf, user_id)

    assert out.nodes[0].credential_ids == {"slack": slack_cred, "google": google_cred}


@pytest.mark.asyncio
async def test_no_required_connections_is_noop():
    node_id, user_id = uuid4(), uuid4()
    wf = _wf(_node(node_id))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({"google": uuid4()}),
        node_def_repo=_FakeNodeDefRepo({node_id: []}),
    )

    out = await uc.execute(wf, user_id)

    assert out is wf  # 변경 없으면 원본 그대로
    assert out.nodes[0].credential_ids == {}


@pytest.mark.asyncio
async def test_resolver_returns_none_leaves_unbound():
    node_id, user_id = uuid4(), uuid4()
    wf = _wf(_node(node_id))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({}),  # 사용자가 google 미연결
        node_def_repo=_FakeNodeDefRepo({node_id: ["google"]}),
    )

    out = await uc.execute(wf, user_id)

    assert out.nodes[0].credential_ids == {}


@pytest.mark.asyncio
async def test_resolver_exception_is_non_fatal():
    node_id, user_id = uuid4(), uuid4()
    wf = _wf(_node(node_id))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({}, raises={"google"}),
        node_def_repo=_FakeNodeDefRepo({node_id: ["google"]}),
    )

    out = await uc.execute(wf, user_id)  # 예외 삼키고 진행

    assert out.nodes[0].credential_ids == {}


@pytest.mark.asyncio
async def test_missing_node_definition_skipped():
    node_id, user_id = uuid4(), uuid4()
    wf = _wf(_node(node_id))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({"google": uuid4()}),
        node_def_repo=_FakeNodeDefRepo({}, missing={node_id}),
    )

    out = await uc.execute(wf, user_id)

    assert out.nodes[0].credential_ids == {}
