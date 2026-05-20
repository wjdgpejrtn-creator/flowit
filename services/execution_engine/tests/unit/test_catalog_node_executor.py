"""CatalogNodeExecutor 단위 테스트 — node_type 조회 → BaseNode.process() 실행 (ADR-0018).

Phase 2b: credential_id가 있으면 inject() → NodeContext.connection_token 적재 →
process() → 평문 토큰 wipe() 까지 검증.
"""
from __future__ import annotations

import dataclasses
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from common_schemas import NodeContext, PlaintextCredential
from common_schemas.enums import RiskLevel
from common_schemas.workflow import NodeConfig, NodeInstance, Position
from nodes_graph.application.catalog_registry import get_all_node_classes
from src.adapters.catalog_node_executor import CatalogNodeExecutor


def _node(parameters=None, credential_id=None):
    return NodeInstance(
        instance_id=uuid4(),
        node_id=uuid4(),
        parameters=parameters or {},
        credential_id=credential_id,
        position=Position(x=0, y=0),
    )


def _config(node_type):
    return NodeConfig(
        node_id=uuid4(),
        node_type=node_type,
        name=node_type,
        category="transform",
        version="1.0.0",
        input_schema={},
        output_schema={},
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="test",
        is_mvp=True,
    )


def _ctx():
    return NodeContext(execution_id=uuid4(), user_id=uuid4())


@pytest.fixture
def executor():
    return CatalogNodeExecutor(get_all_node_classes())


class TestCatalogNodeExecutorDomain:
    def test_executes_domain_node(self, executor):
        """domain 노드(json_extract)를 async process()로 실행 → dict 반환."""
        out = executor.execute(
            node=_node(),
            config=_config("json_extract"),
            inputs={"data": {"user": {"name": "아름"}}, "path": "user.name"},
            context=_ctx(),
        )
        assert out == {"value": "아름", "found": True}

    def test_merges_parameters_and_inputs(self, executor):
        """node.parameters + 런타임 inputs 병합 후 input_schema로 변환."""
        out = executor.execute(
            node=_node(parameters={"data": {"k": 1}}),
            config=_config("json_extract"),
            inputs={"path": "k"},
            context=_ctx(),
        )
        assert out == {"value": 1, "found": True}

    def test_ignores_keys_absent_from_input_schema(self, executor):
        """input_schema에 없는 키는 무시."""
        out = executor.execute(
            node=_node(),
            config=_config("if_condition"),
            inputs={"left": 5, "operator": "eq", "right": 5, "extra": "x"},
            context=_ctx(),
        )
        assert out["branch"] == "true"

    def test_context_passed_without_error(self, executor):
        """domain 노드는 context를 무시하지만 시그니처 전달 경로는 정상."""
        out = executor.execute(
            node=_node(),
            config=_config("number_calc"),
            inputs={"operation": "add", "operands": [1.0, 2.0]},
            context=_ctx(),
        )
        assert out["result"] == 3.0


class TestCatalogNodeExecutorErrors:
    def test_unknown_node_type_raises(self, executor):
        with pytest.raises(ValueError, match="미등록 node_type"):
            executor.execute(
                node=_node(),
                config=_config("does_not_exist"),
                inputs={},
                context=_ctx(),
            )

    # ADR-0018 Phase 3d로 external 53종 전부 process() 실구현 완료 — NotImplementedError
    # 스텁 노드가 더 이상 없다. process() 예외 전파는 test_wipes_credential_when_process_raises
    # 가 커버한다.


# --- credential 주입 (Phase 2b) -------------------------------------------------

@dataclasses.dataclass
class _FakeInput:
    value: int = 0
    should_raise: bool = False


@dataclasses.dataclass
class _FakeOutput:
    seen_token: str | None
    echo: int


class _FakeNode:
    """connection_token을 출력으로 되돌려 process()가 토큰을 봤는지 확인 가능한 노드."""

    input_schema = _FakeInput

    async def process(self, node_input: _FakeInput, context: NodeContext) -> _FakeOutput:
        if node_input.should_raise:
            raise RuntimeError("node boom")
        return _FakeOutput(seen_token=context.connection_token, echo=node_input.value)


class _FakeCredentialService:
    def __init__(self, credential: PlaintextCredential, captured: dict) -> None:
        self._credential = credential
        self._captured = captured

    async def inject(self, credential_id, node_id) -> PlaintextCredential:
        self._captured["inject_args"] = (credential_id, node_id)
        return self._credential


def _factory(credential: PlaintextCredential, captured: dict):
    @asynccontextmanager
    async def factory():
        captured["factory_entered"] = True
        yield _FakeCredentialService(credential, captured)

    return factory


def _credential(value: str = "tok-abc") -> PlaintextCredential:
    return PlaintextCredential(
        credential_id=str(uuid4()), credential_kind="aes_gcm", value=value
    )


class TestCatalogNodeExecutorCredential:
    def test_injects_token_into_context(self):
        """credential_id 있으면 inject() → process()가 connection_token을 본다."""
        captured: dict = {}
        executor = CatalogNodeExecutor(
            {"fake": _FakeNode}, credential_service_factory=_factory(_credential("tok-abc"), captured)
        )
        node = _node(credential_id=uuid4())

        out = executor.execute(
            node=node, config=_config("fake"), inputs={"value": 7}, context=_ctx()
        )

        assert out["seen_token"] == "tok-abc"
        assert out["echo"] == 7
        # inject()는 credential_id + NodeDefinition id(node.node_id)로 호출된다.
        assert captured["inject_args"] == (node.credential_id, node.node_id)

    def test_wipes_credential_and_context_after_success(self):
        """process() 정상 종료 후 평문 토큰이 credential·context 양쪽에서 제거된다."""
        captured: dict = {}
        credential = _credential("secret-tok")
        ctx = _ctx()
        executor = CatalogNodeExecutor(
            {"fake": _FakeNode}, credential_service_factory=_factory(credential, captured)
        )

        executor.execute(
            node=_node(credential_id=uuid4()), config=_config("fake"), inputs={}, context=ctx
        )

        assert credential.value == ""
        assert ctx.connection_token is None

    def test_wipes_credential_when_process_raises(self):
        """process()가 예외를 던져도 finally에서 평문 토큰이 제거된다."""
        captured: dict = {}
        credential = _credential("secret-tok")
        ctx = _ctx()
        executor = CatalogNodeExecutor(
            {"fake": _FakeNode}, credential_service_factory=_factory(credential, captured)
        )

        with pytest.raises(RuntimeError, match="node boom"):
            executor.execute(
                node=_node(credential_id=uuid4()),
                config=_config("fake"),
                inputs={"should_raise": True},
                context=ctx,
            )

        assert credential.value == ""
        assert ctx.connection_token is None

    def test_no_credential_skips_factory(self):
        """credential_id=None이면 factory를 호출하지 않는다."""
        captured: dict = {}
        executor = CatalogNodeExecutor(
            {"fake": _FakeNode}, credential_service_factory=_factory(_credential(), captured)
        )

        out = executor.execute(
            node=_node(credential_id=None), config=_config("fake"), inputs={"value": 3}, context=_ctx()
        )

        assert out["seen_token"] is None
        assert "factory_entered" not in captured

    def test_credential_node_without_factory_raises(self):
        """credential_id는 있는데 factory가 미배선이면 명확한 RuntimeError."""
        executor = CatalogNodeExecutor({"fake": _FakeNode})

        with pytest.raises(RuntimeError, match="credential_service_factory"):
            executor.execute(
                node=_node(credential_id=uuid4()),
                config=_config("fake"),
                inputs={},
                context=_ctx(),
            )
