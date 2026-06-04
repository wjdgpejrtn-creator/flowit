from uuid import uuid4

import pytest
from common_schemas import Edge, NodeInstance, Position, WorkflowSchema
from common_schemas.enums import ErrorCode, RiskLevel
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.services.graph_validator import GraphValidator


class _InMemoryRepo:
    def __init__(self):
        self._store = {}

    async def upsert(self, d):
        self._store[str(d.node_id)] = d
        return d
    async def list_all(self, mvp_only=False): return list(self._store.values())
    async def get_by_id(self, node_id): return self._store.get(str(node_id))
    async def search_by_embedding(self, q, limit=10): return list(self._store.values())[:limit]


def _make_node_def(required_connections=None, input_schema=None):
    from uuid import uuid4
    return NodeDefinition(
        node_id=uuid4(), node_type="x", name="x", category="x", version="1.0.0",
        input_schema=input_schema or {}, output_schema={}, parameter_schema={},
        risk_level=RiskLevel.LOW, required_connections=required_connections or [],
        description="x", is_mvp=True,
    )


def _wf(nodes, edges):
    return WorkflowSchema(
        workflow_id=uuid4(), name="test", scope="private", is_draft=False,
        nodes=nodes, connections=edges,
    )


def _node(node_id=None, credential_id=None, parameters=None):
    return NodeInstance(
        instance_id=uuid4(), node_id=node_id or uuid4(),
        parameters=parameters or {}, credential_id=credential_id, position=Position(x=0, y=0),
    )


def _edge(f, t):
    return Edge(from_instance_id=f, to_instance_id=t, from_handle="out", to_handle="in")


@pytest.mark.asyncio
async def test_valid_graph_passes():
    n1, n2 = _node(), _node()
    result = await GraphValidator(_InMemoryRepo()).validate(_wf([n1, n2], [_edge(n1.instance_id, n2.instance_id)]))
    assert result.validation_status == "passed"


@pytest.mark.asyncio
async def test_cycle_detected():
    n1, n2, n3 = _node(), _node(), _node()
    edges = [
        _edge(n1.instance_id, n2.instance_id),
        _edge(n2.instance_id, n3.instance_id),
        _edge(n3.instance_id, n1.instance_id),
    ]
    result = await GraphValidator(_InMemoryRepo()).validate(_wf([n1, n2, n3], edges))
    assert result.validation_status == "failed"
    assert any(e.code == ErrorCode.E_CYCLE_DETECTED for e in result.errors)


@pytest.mark.asyncio
async def test_isolated_node_detected():
    n1, n2, n3 = _node(), _node(), _node()
    result = await GraphValidator(_InMemoryRepo()).validate(_wf([n1, n2, n3], [_edge(n1.instance_id, n2.instance_id)]))
    assert result.validation_status == "failed"
    isolated = next(e for e in result.errors if e.code == ErrorCode.E_ISOLATED_NODE)
    assert str(n3.instance_id) in isolated.node_ids


@pytest.mark.asyncio
async def test_duplicate_instance_id_detected():
    shared = uuid4()
    n1 = NodeInstance(instance_id=shared, node_id=uuid4(), parameters={}, position=Position(x=0, y=0))
    n2 = NodeInstance(instance_id=shared, node_id=uuid4(), parameters={}, position=Position(x=1, y=1))
    result = await GraphValidator(_InMemoryRepo()).validate(_wf([n1, n2], []))
    assert any(e.code == ErrorCode.E_DUPLICATE_ID for e in result.errors)


@pytest.mark.asyncio
async def test_missing_required_connection_detected():
    repo = _InMemoryRepo()
    node_def = _make_node_def(required_connections=["google"])
    await repo.upsert(node_def)
    ni = _node(node_id=node_def.node_id, credential_id=None)
    result = await GraphValidator(repo).validate(_wf([ni], []))
    assert any(e.code == ErrorCode.E_MISSING_CONNECTION for e in result.errors)


@pytest.mark.asyncio
async def test_required_connection_with_credential_passes():
    repo = _InMemoryRepo()
    node_def = _make_node_def(required_connections=["google"])
    await repo.upsert(node_def)
    ni = _node(node_id=node_def.node_id, credential_id=uuid4())
    other = _node()
    result = await GraphValidator(repo).validate(_wf([ni, other], [_edge(ni.instance_id, other.instance_id)]))
    assert result.validation_status == "passed"


@pytest.mark.asyncio
async def test_single_node_no_isolated_error():
    n1 = _node()
    result = await GraphValidator(_InMemoryRepo()).validate(_wf([n1], []))
    assert not any(e.code == ErrorCode.E_ISOLATED_NODE for e in result.errors)


@pytest.mark.asyncio
async def test_missing_required_parameter_detected():
    """input_schema.required 중 NodeInstance.parameters에 없는 필드는 검증 실패."""
    repo = _InMemoryRepo()
    schema = {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]}
    node_def = _make_node_def(input_schema=schema)
    await repo.upsert(node_def)
    ni = _node(node_id=node_def.node_id, parameters={})  # prompt 누락
    result = await GraphValidator(repo).validate(_wf([ni], []))
    assert result.validation_status == "failed"
    err = next(e for e in result.errors if e.code == ErrorCode.E_MISSING_REQUIRED_PARAMETER)
    assert "prompt" in err.message
    assert str(ni.instance_id) in err.node_ids


@pytest.mark.asyncio
async def test_required_parameter_empty_string_detected():
    """빈 문자열도 누락으로 취급 (frontend computeMissingRequired와 동일)."""
    repo = _InMemoryRepo()
    schema = {"required": ["prompt"], "properties": {"prompt": {"type": "string"}}}
    node_def = _make_node_def(input_schema=schema)
    await repo.upsert(node_def)
    ni = _node(node_id=node_def.node_id, parameters={"prompt": ""})
    result = await GraphValidator(repo).validate(_wf([ni], []))
    assert any(e.code == ErrorCode.E_MISSING_REQUIRED_PARAMETER for e in result.errors)


@pytest.mark.asyncio
async def test_required_parameter_present_passes():
    repo = _InMemoryRepo()
    schema = {"required": ["prompt"], "properties": {"prompt": {"type": "string"}}}
    node_def = _make_node_def(input_schema=schema)
    await repo.upsert(node_def)
    ni = _node(node_id=node_def.node_id, parameters={"prompt": "hello"})
    result = await GraphValidator(repo).validate(_wf([ni], []))
    assert not any(e.code == ErrorCode.E_MISSING_REQUIRED_PARAMETER for e in result.errors)


@pytest.mark.asyncio
async def test_required_parameter_aggregates_multiple_fields():
    repo = _InMemoryRepo()
    schema = {"required": ["a", "b"], "properties": {"a": {}, "b": {}, "c": {}}}
    node_def = _make_node_def(input_schema=schema)
    await repo.upsert(node_def)
    ni = _node(node_id=node_def.node_id, parameters={"c": "ok"})
    result = await GraphValidator(repo).validate(_wf([ni], []))
    err = next(e for e in result.errors if e.code == ErrorCode.E_MISSING_REQUIRED_PARAMETER)
    assert "'a'" in err.message and "'b'" in err.message


@pytest.mark.asyncio
async def test_required_parameter_skipped_when_no_required_key():
    repo = _InMemoryRepo()
    node_def = _make_node_def(input_schema={"properties": {"x": {}}})  # required 키 없음
    await repo.upsert(node_def)
    ni = _node(node_id=node_def.node_id, parameters={})
    result = await GraphValidator(repo).validate(_wf([ni], []))
    assert not any(e.code == ErrorCode.E_MISSING_REQUIRED_PARAMETER for e in result.errors)


@pytest.mark.asyncio
async def test_type_compatibility_returns_no_errors():
    # _check_type_compatibility는 현재 stub — 항상 빈 리스트 반환
    n1, n2 = _node(), _node()
    edge = _edge(n1.instance_id, n2.instance_id)
    result = await GraphValidator(_InMemoryRepo()).validate(_wf([n1, n2], [edge]))
    assert not any(e.code for e in result.errors if e.validator == "TypeCompatibility")
    assert result.validation_status == "passed"


@pytest.mark.asyncio
async def test_multi_connection_partial_binding_reports_missing():
    """멀티커넥션 노드에 일부 provider만 바인딩 → 빠진 provider만 정확히 보고 (REQ-012)."""
    repo = _InMemoryRepo()
    node_def = _make_node_def(required_connections=["slack", "google"])
    await repo.upsert(node_def)
    ni = NodeInstance(
        instance_id=uuid4(), node_id=node_def.node_id, parameters={},
        credential_ids={"slack": uuid4()}, position=Position(x=0, y=0),
    )
    result = await GraphValidator(repo).validate(_wf([ni], []))
    errs = [e for e in result.errors if e.code == ErrorCode.E_MISSING_CONNECTION]
    assert len(errs) == 1
    assert "google" in errs[0].message
    assert "slack" not in errs[0].message


@pytest.mark.asyncio
async def test_multi_connection_full_binding_passes():
    """credential_ids로 required provider 전부 바인딩 → 통과."""
    repo = _InMemoryRepo()
    node_def = _make_node_def(required_connections=["slack", "google"])
    await repo.upsert(node_def)
    ni = NodeInstance(
        instance_id=uuid4(), node_id=node_def.node_id, parameters={},
        credential_ids={"slack": uuid4(), "google": uuid4()}, position=Position(x=0, y=0),
    )
    other = _node()
    result = await GraphValidator(repo).validate(_wf([ni, other], [_edge(ni.instance_id, other.instance_id)]))
    assert result.validation_status == "passed"


@pytest.mark.asyncio
async def test_credential_ids_single_provider_passes():
    """단일 required를 legacy credential_id가 아닌 credential_ids로 바인딩해도 통과."""
    repo = _InMemoryRepo()
    node_def = _make_node_def(required_connections=["google"])
    await repo.upsert(node_def)
    ni = NodeInstance(
        instance_id=uuid4(), node_id=node_def.node_id, parameters={},
        credential_ids={"google": uuid4()}, position=Position(x=0, y=0),
    )
    other = _node()
    result = await GraphValidator(repo).validate(_wf([ni, other], [_edge(ni.instance_id, other.instance_id)]))
    assert result.validation_status == "passed"
