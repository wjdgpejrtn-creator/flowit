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
async def test_preserves_binding_matching_active():
    """바인딩된 id가 현재 active connection과 같으면 보존(불필요한 변경 없음)."""
    node_id, user_id, active = uuid4(), uuid4(), uuid4()
    wf = _wf(_node(node_id, credential_ids={"google": active}))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({"google": active}),
        node_def_repo=_FakeNodeDefRepo({node_id: ["google"]}),
    )

    out = await uc.execute(wf, user_id)

    assert out is wf  # 변경 없음
    assert out.nodes[0].credential_ids == {"google": active}


@pytest.mark.asyncio
async def test_rebinds_stale_credential_to_active():
    """과거 연결 해제로 죽은 id가 박혀 있으면 현재 active connection으로 교정(MED 리뷰 #1)."""
    node_id, user_id = uuid4(), uuid4()
    stale = uuid4()   # 재연결 전 죽은 credential_id (저장본에 잔존)
    active = uuid4()  # 재연결 후 현재 active connection
    wf = _wf(_node(node_id, credential_ids={"google": stale}))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({"google": active}),
        node_def_repo=_FakeNodeDefRepo({node_id: ["google"]}),
    )

    out = await uc.execute(wf, user_id)

    assert out.nodes[0].credential_ids == {"google": active}


@pytest.mark.asyncio
async def test_rebinds_stale_legacy_credential_id():
    """legacy 단일 credential_id가 stale이면 credential_ids[provider]로 교정(precedence)."""
    node_id, user_id = uuid4(), uuid4()
    stale_legacy = uuid4()
    active = uuid4()
    wf = _wf(_node(node_id, credential_id=stale_legacy))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({"google": active}),
        node_def_repo=_FakeNodeDefRepo({node_id: ["google"]}),
    )

    out = await uc.execute(wf, user_id)

    # credential_ids가 legacy credential_id보다 우선하므로 active로 해소된다
    assert out.nodes[0].resolve_credentials(["google"]) == {"google": active}


@pytest.mark.asyncio
async def test_multi_provider_binds_only_unsynced():
    node_id, user_id = uuid4(), uuid4()
    slack_cred, google_cred = uuid4(), uuid4()
    # slack은 이미 active와 일치(보존), google은 미바인딩(채움)
    wf = _wf(_node(node_id, credential_ids={"slack": slack_cred}))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({"google": google_cred, "slack": slack_cred}),
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
async def test_no_active_preserves_existing_binding():
    """active connection이 없으면(미연결) 기존 바인딩은 건드리지 않는다(해소 불가)."""
    node_id, user_id, existing = uuid4(), uuid4(), uuid4()
    wf = _wf(_node(node_id, credential_ids={"google": existing}))
    uc = AutobindConnectionsUseCase(
        resolver=_FakeResolver({}),  # 미연결
        node_def_repo=_FakeNodeDefRepo({node_id: ["google"]}),
    )

    out = await uc.execute(wf, user_id)

    assert out is wf
    assert out.nodes[0].credential_ids == {"google": existing}


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
