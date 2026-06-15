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


def _make_node_def(required_connections=None, input_schema=None, output_schema=None, category="x"):
    from uuid import uuid4
    return NodeDefinition(
        node_id=uuid4(), node_type="x", name="x", category=category, version="1.0.0",
        input_schema=input_schema or {}, output_schema=output_schema or {}, parameter_schema={},
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


def _register(repo, *nodes, category="x"):
    """노드들의 node_id로 generic NodeDefinition을 repo에 등록 (존재 검증 충족용).

    E_UNKNOWN_NODE_TYPE 추가(ADR-0026 §6.6)로 '통과' 기대 테스트의 모든 노드는 카탈로그
    (repo)에 실재해야 한다. 검증 초점이 아닌 보조 노드를 일괄 등록한다. validator는 get_by_id
    결과의 category/required_connections/input_schema만 보므로 def.node_id 불일치는 무관.
    """
    for n in nodes:
        repo._store[str(n.node_id)] = _make_node_def(category=category)


@pytest.mark.asyncio
async def test_valid_graph_passes():
    repo = _InMemoryRepo()
    n1, n2 = _node(), _node()
    _register(repo, n1, n2)
    result = await GraphValidator(repo).validate(_wf([n1, n2], [_edge(n1.instance_id, n2.instance_id)]))
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


# ── ADR-0023 L3: 유한 순환(품질게이트 루프) 완화 ──────────────────────────
# 엔진 CyclicScheduler 수용 기준 미러: non-trivial SCC는 condition 노드 ≥1개면 허용,
# 없으면 E_CYCLE_DETECTED. (진짜 파리티 테스트 — validate() passed ⟺ CyclicScheduler
# .plan() non-raise — 는 둘 다 import 가능한 조립 계층(execution_engine/api_server)에 둔다.)


def _condition_node(repo_def):
    """repo에 등록된 condition NodeDefinition을 참조하는 NodeInstance."""
    return _node(node_id=repo_def.node_id)


@pytest.mark.asyncio
async def test_cycle_with_condition_node_passes():
    """gen → cond, cond → gen(back-edge). cond가 category='condition'이면 탈출 가능 → 통과."""
    repo = _InMemoryRepo()
    cond_def = _make_node_def(category="condition")
    await repo.upsert(cond_def)
    gen, cond = _node(), _condition_node(cond_def)
    _register(repo, gen)
    edges = [_edge(gen.instance_id, cond.instance_id), _edge(cond.instance_id, gen.instance_id)]
    result = await GraphValidator(repo).validate(_wf([gen, cond], edges))
    assert not any(e.code == ErrorCode.E_CYCLE_DETECTED for e in result.errors)
    assert result.validation_status == "passed"


@pytest.mark.asyncio
async def test_cycle_without_condition_node_rejected():
    """2-노드 순환에 condition 노드 없음 → 탈출 불가 → E_CYCLE_DETECTED."""
    a, b = _node(), _node()
    edges = [_edge(a.instance_id, b.instance_id), _edge(b.instance_id, a.instance_id)]
    result = await GraphValidator(_InMemoryRepo()).validate(_wf([a, b], edges))
    assert any(e.code == ErrorCode.E_CYCLE_DETECTED for e in result.errors)


@pytest.mark.asyncio
async def test_condition_self_loop_passes():
    """condition 노드 self-loop → 탈출 조건 보유 → 통과."""
    repo = _InMemoryRepo()
    cond_def = _make_node_def(category="condition")
    await repo.upsert(cond_def)
    cond = _condition_node(cond_def)
    other = _node()
    edges = [_edge(cond.instance_id, cond.instance_id), _edge(cond.instance_id, other.instance_id)]
    result = await GraphValidator(repo).validate(_wf([cond, other], edges))
    assert not any(e.code == ErrorCode.E_CYCLE_DETECTED for e in result.errors)


@pytest.mark.asyncio
async def test_non_condition_self_loop_rejected():
    """비-condition 노드 self-loop → 탈출 불가 → E_CYCLE_DETECTED."""
    a = _node()
    other = _node()
    edges = [_edge(a.instance_id, a.instance_id), _edge(a.instance_id, other.instance_id)]
    result = await GraphValidator(_InMemoryRepo()).validate(_wf([a, other], edges))
    assert any(e.code == ErrorCode.E_CYCLE_DETECTED for e in result.errors)


@pytest.mark.asyncio
async def test_two_cycles_one_missing_condition_rejected():
    """SCC 2개 — 하나는 condition 보유, 하나는 누락 → 누락된 쪽 때문에 E_CYCLE_DETECTED."""
    repo = _InMemoryRepo()
    cond_def = _make_node_def(category="condition")
    await repo.upsert(cond_def)
    # 루프1: gen↔cond (탈출 가능)
    gen, cond = _node(), _condition_node(cond_def)
    # 루프2: x↔y (탈출 불가)
    x, y = _node(), _node()
    bridge = _edge(cond.instance_id, x.instance_id)  # 두 SCC 연결 (고립 방지)
    edges = [
        _edge(gen.instance_id, cond.instance_id), _edge(cond.instance_id, gen.instance_id),
        bridge,
        _edge(x.instance_id, y.instance_id), _edge(y.instance_id, x.instance_id),
    ]
    result = await GraphValidator(repo).validate(_wf([gen, cond, x, y], edges))
    cyc = next(e for e in result.errors if e.code == ErrorCode.E_CYCLE_DETECTED)
    assert str(x.instance_id) in cyc.node_ids
    assert str(gen.instance_id) not in cyc.node_ids  # 탈출 가능한 루프는 보고 안 함


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
    _register(repo, other)
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
    # 스키마 미선언(generic) 노드 + 표현식 없음 → 타입 검증 대상 없음 → 통과
    repo = _InMemoryRepo()
    n1, n2 = _node(), _node()
    _register(repo, n1, n2)
    edge = _edge(n1.instance_id, n2.instance_id)
    result = await GraphValidator(repo).validate(_wf([n1, n2], [edge]))
    assert not any(e.code == ErrorCode.E_NODE_TYPE_MISMATCH for e in result.errors)
    assert result.validation_status == "passed"


# ── 표현식경로 shape 타입 검증 (REQ-003, _check_type_compatibility 1차) ──────────
# 신정혜 요청 + 조장 전수조사 결정: edge handle은 제어 분기 라벨이라 무의미하고, 실제 IO
# 불일치는 parameters의 ${instance_id.field} 표현식 경로에서 발생한다. 1차 스코프 = shape
# 레벨(scalar↔array↔object). nested items / ANY({}) 필드는 보수적 통과(false positive 방지).


def _typed_def(repo, *, inputs=None, outputs=None):
    """input/output schema의 properties 타입을 지정한 NodeDefinition을 repo에 등록."""
    d = _make_node_def(
        input_schema={"properties": inputs or {}},
        output_schema={"properties": outputs or {}},
    )
    repo._store[str(d.node_id)] = d
    return d


@pytest.mark.asyncio
async def test_type_mismatch_array_output_to_scalar_param_detected():
    """upstream 출력이 array인데 소비 파라미터 기대가 string(scalar) → E_NODE_TYPE_MISMATCH."""
    repo = _InMemoryRepo()
    src_def = _typed_def(repo, outputs={"values": {"type": "array"}})
    dst_def = _typed_def(repo, inputs={"body": {"type": "string"}})
    src = _node(node_id=src_def.node_id)
    dst = _node(node_id=dst_def.node_id, parameters={"body": f"${{{src.instance_id}.values}}"})
    result = await GraphValidator(repo).validate(
        _wf([src, dst], [_edge(src.instance_id, dst.instance_id)])
    )
    err = next(e for e in result.errors if e.code == ErrorCode.E_NODE_TYPE_MISMATCH)
    assert err.validator == "SchemaValidation"
    assert str(dst.instance_id) in err.node_ids


@pytest.mark.asyncio
async def test_type_mismatch_object_output_to_array_param_detected():
    """object → array shape 불일치도 검출."""
    repo = _InMemoryRepo()
    src_def = _typed_def(repo, outputs={"data": {"type": "object"}})
    dst_def = _typed_def(repo, inputs={"items": {"type": "array"}})
    src = _node(node_id=src_def.node_id)
    dst = _node(node_id=dst_def.node_id, parameters={"items": f"${{{src.instance_id}.data}}"})
    result = await GraphValidator(repo).validate(
        _wf([src, dst], [_edge(src.instance_id, dst.instance_id)])
    )
    assert any(e.code == ErrorCode.E_NODE_TYPE_MISMATCH for e in result.errors)


@pytest.mark.asyncio
async def test_type_compat_scalar_to_scalar_passes():
    """integer → string은 scalar끼리라 1차 shape 레벨에서 통과(캐스팅/보간 흔함)."""
    repo = _InMemoryRepo()
    src_def = _typed_def(repo, outputs={"count": {"type": "integer"}})
    dst_def = _typed_def(repo, inputs={"text": {"type": "string"}})
    src = _node(node_id=src_def.node_id)
    dst = _node(node_id=dst_def.node_id, parameters={"text": f"${{{src.instance_id}.count}}"})
    result = await GraphValidator(repo).validate(
        _wf([src, dst], [_edge(src.instance_id, dst.instance_id)])
    )
    assert not any(e.code == ErrorCode.E_NODE_TYPE_MISMATCH for e in result.errors)


@pytest.mark.asyncio
async def test_type_compat_array_to_array_passes_first_pass():
    """1차는 shape 레벨 — array→array는 통과(nested items 정밀 검증은 2차 스코프)."""
    repo = _InMemoryRepo()
    src_def = _typed_def(repo, outputs={"values": {"type": "array"}})
    dst_def = _typed_def(repo, inputs={"rows": {"type": "array"}})
    src = _node(node_id=src_def.node_id)
    dst = _node(node_id=dst_def.node_id, parameters={"rows": f"${{{src.instance_id}.values}}"})
    result = await GraphValidator(repo).validate(
        _wf([src, dst], [_edge(src.instance_id, dst.instance_id)])
    )
    assert not any(e.code == ErrorCode.E_NODE_TYPE_MISMATCH for e in result.errors)


@pytest.mark.asyncio
async def test_type_compat_any_output_skipped():
    """출력 필드 타입 미선언({} = ANY) → 보수적 통과(false positive 방지)."""
    repo = _InMemoryRepo()
    src_def = _typed_def(repo, outputs={"result": {}})  # ANY
    dst_def = _typed_def(repo, inputs={"text": {"type": "string"}})
    src = _node(node_id=src_def.node_id)
    dst = _node(node_id=dst_def.node_id, parameters={"text": f"${{{src.instance_id}.result}}"})
    result = await GraphValidator(repo).validate(
        _wf([src, dst], [_edge(src.instance_id, dst.instance_id)])
    )
    assert not any(e.code == ErrorCode.E_NODE_TYPE_MISMATCH for e in result.errors)


@pytest.mark.asyncio
async def test_type_compat_string_interpolation_relaxed():
    """값 전체가 아닌 문자열 보간 안의 참조는 str 컨텍스트 → 검증 완화(통과)."""
    repo = _InMemoryRepo()
    src_def = _typed_def(repo, outputs={"values": {"type": "array"}})
    dst_def = _typed_def(repo, inputs={"body": {"type": "string"}})
    src = _node(node_id=src_def.node_id)
    dst = _node(
        node_id=dst_def.node_id,
        parameters={"body": f"Total: ${{{src.instance_id}.values}} rows"},
    )
    result = await GraphValidator(repo).validate(
        _wf([src, dst], [_edge(src.instance_id, dst.instance_id)])
    )
    assert not any(e.code == ErrorCode.E_NODE_TYPE_MISMATCH for e in result.errors)


@pytest.mark.asyncio
async def test_type_compat_unresolved_token_skipped():
    """토큰이 instance_id(UUID)가 아니면(rewrite 전 잔재) 검증 skip."""
    repo = _InMemoryRepo()
    dst_def = _typed_def(repo, inputs={"text": {"type": "string"}})
    dst = _node(node_id=dst_def.node_id, parameters={"text": "${some_node.values}"})
    other = _node()
    _register(repo, other)
    result = await GraphValidator(repo).validate(
        _wf([dst, other], [_edge(dst.instance_id, other.instance_id)])
    )
    assert not any(e.code == ErrorCode.E_NODE_TYPE_MISMATCH for e in result.errors)


# ── list 원소 표현식 검증 (staging 실데이터 기반, 2026-06-15 덤프) ────────────────
# 실제 데이터 흐름의 주류가 to:["${x.field}"] / operands:["${x.field}", ...] 처럼 list
# 원소 표현식이라, 기대 shape는 properties[param].items.type 으로 본다. (이메일/id 등
# 민감값은 익명 UUID로 마스킹 — 표현식 구조만 보존)


@pytest.mark.asyncio
async def test_type_mismatch_list_element_array_to_scalar_detected():
    """number_calc operands(array[number])에 array 출력(values)이 원소로 유입 → 불일치 검출.

    staging: number_calc operands: ["${<sheets>.values}", "전주 데이터"] 패턴.
    """
    repo = _InMemoryRepo()
    sheets_def = _typed_def(repo, outputs={"values": {"type": "array"}})
    calc_def = _typed_def(
        repo, inputs={"operands": {"type": "array", "items": {"type": "number"}}}
    )
    sheets = _node(node_id=sheets_def.node_id)
    calc = _node(
        node_id=calc_def.node_id,
        parameters={"operands": [f"${{{sheets.instance_id}.values}}", "전주 데이터"]},
    )
    result = await GraphValidator(repo).validate(
        _wf([sheets, calc], [_edge(sheets.instance_id, calc.instance_id)])
    )
    err = next(e for e in result.errors if e.code == ErrorCode.E_NODE_TYPE_MISMATCH)
    assert "operands" in err.message
    assert str(calc.instance_id) in err.node_ids


@pytest.mark.asyncio
async def test_type_compat_list_element_scalar_to_scalar_passes():
    """gmail_send to(array[string]) 원소가 scalar 출력 표현식 → 통과."""
    repo = _InMemoryRepo()
    src_def = _typed_def(repo, outputs={"email": {"type": "string"}})
    gmail_def = _typed_def(
        repo, inputs={"to": {"type": "array", "items": {"type": "string"}}}
    )
    src = _node(node_id=src_def.node_id)
    gmail = _node(
        node_id=gmail_def.node_id,
        parameters={"to": [f"${{{src.instance_id}.email}}"]},
    )
    result = await GraphValidator(repo).validate(
        _wf([src, gmail], [_edge(src.instance_id, gmail.instance_id)])
    )
    assert not any(e.code == ErrorCode.E_NODE_TYPE_MISMATCH for e in result.errors)


@pytest.mark.asyncio
async def test_type_compat_list_element_nested_path_conservative_pass():
    """to:["${x.items.email}"] 같은 nested path는 top-level properties에 없어 보수적 통과.

    staging to=None의 실제 원인(nested 경로 환각)이지만, 이는 경로 존재성 문제라 1차
    shape 검증 영역이 아님(후속 표현식 경로 검증 몫) — false positive를 내지 않아야 한다.
    """
    repo = _InMemoryRepo()
    src_def = _typed_def(repo, outputs={"messages": {"type": "array"}})
    gmail_def = _typed_def(
        repo, inputs={"to": {"type": "array", "items": {"type": "string"}}}
    )
    src = _node(node_id=src_def.node_id)
    gmail = _node(
        node_id=gmail_def.node_id,
        parameters={"to": [f"${{{src.instance_id}.items.email}}"]},
    )
    result = await GraphValidator(repo).validate(
        _wf([src, gmail], [_edge(src.instance_id, gmail.instance_id)])
    )
    assert not any(e.code == ErrorCode.E_NODE_TYPE_MISMATCH for e in result.errors)


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
    _register(repo, other)
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
    _register(repo, other)
    result = await GraphValidator(repo).validate(_wf([ni, other], [_edge(ni.instance_id, other.instance_id)]))
    assert result.validation_status == "passed"


# ── ADR-0026 §6.6: 비실재 노드 검증 게이트 ──────────────────────────────────
@pytest.mark.asyncio
async def test_unknown_node_rejected():
    """node_id가 카탈로그에 없으면 E_UNKNOWN_NODE_TYPE으로 거부 (LLM 비실재 노드 차단)."""
    repo = _InMemoryRepo()
    known, unknown = _node(), _node()
    _register(repo, known)  # unknown은 일부러 미등록
    result = await GraphValidator(repo).validate(
        _wf([known, unknown], [_edge(known.instance_id, unknown.instance_id)])
    )
    assert result.validation_status == "failed"
    err = next(e for e in result.errors if e.code == ErrorCode.E_UNKNOWN_NODE_TYPE)
    assert str(unknown.instance_id) in err.node_ids
    assert str(known.instance_id) not in err.node_ids


@pytest.mark.asyncio
async def test_all_known_nodes_no_unknown_error():
    repo = _InMemoryRepo()
    n1, n2 = _node(), _node()
    _register(repo, n1, n2)
    result = await GraphValidator(repo).validate(
        _wf([n1, n2], [_edge(n1.instance_id, n2.instance_id)])
    )
    assert not any(e.code == ErrorCode.E_UNKNOWN_NODE_TYPE for e in result.errors)
