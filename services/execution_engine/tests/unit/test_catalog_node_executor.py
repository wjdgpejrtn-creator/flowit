"""CatalogNodeExecutor 단위 테스트 — node_type 조회 → BaseNode.process() 실행 (ADR-0018).

Phase 2b: credential_id가 있으면 inject() → NodeContext.connection_token 적재 →
process() → 평문 토큰 wipe() 까지 검증.
"""
from __future__ import annotations

import dataclasses
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from common_schemas import NodeContext, PlaintextCredential, SkillDocument
from common_schemas.enums import RiskLevel
from common_schemas.workflow import NodeConfig, NodeInstance, Position
from nodes_graph.application.catalog_registry import get_all_node_classes
from src.adapters.catalog_node_executor import CatalogNodeExecutor


def _node(parameters=None, credential_id=None, skill_id=None):
    return NodeInstance(
        instance_id=uuid4(),
        node_id=uuid4(),
        parameters=parameters or {},
        credential_id=credential_id,
        skill_id=skill_id,
        position=Position(x=0, y=0),
    )


def _config(node_type, category="transform"):
    return NodeConfig(
        node_id=uuid4(),
        node_type=node_type,
        name=node_type,
        category=category,
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


# --- skill 지침서 주입 (REQ-013) ------------------------------------------------

@dataclasses.dataclass
class _SystemInput:
    """system 프롬프트를 받는 LLM 계열 노드의 input (anthropic_chat 미러)."""

    system: str | None = None
    value: int = 0


@dataclasses.dataclass
class _SystemOutput:
    seen_system: str | None
    echo: int


class _SystemNode:
    """process()가 받은 system을 출력으로 되돌려 주입 결과를 확인 가능한 LLM 계열 노드."""

    input_schema = _SystemInput

    async def process(self, node_input: _SystemInput, context: NodeContext) -> _SystemOutput:
        return _SystemOutput(seen_system=node_input.system, echo=node_input.value)


class _FakeSkillStore:
    def __init__(self, document: SkillDocument | None = None, raises: bool = False) -> None:
        self._document = document
        self._raises = raises
        self.load_calls: list = []

    async def load(self, skill_id):
        self.load_calls.append(skill_id)
        if self._raises:
            raise RuntimeError("gcs boom")
        return self._document


def _skill_doc(instructions: str = "너는 세무 전문가다.") -> SkillDocument:
    return SkillDocument(
        skill_id=uuid4(), name="tax-expert", description="세무 도메인 지침", instructions=instructions
    )


class TestCatalogNodeExecutorSkillInjection:
    def test_injects_instructions_into_empty_system(self):
        """skill_id + ai 노드: 기존 system이 없으면 instructions가 그대로 system이 된다."""
        store = _FakeSkillStore(_skill_doc("너는 세무 전문가다."))
        executor = CatalogNodeExecutor({"fake": _SystemNode}, skill_document_store=store)

        out = executor.execute(
            node=_node(skill_id=uuid4()),
            config=_config("fake", category="ai"),
            inputs={"value": 1},
            context=_ctx(),
        )

        assert out["seen_system"] == "너는 세무 전문가다."
        assert len(store.load_calls) == 1

    def test_prepends_instructions_before_existing_system(self):
        """기존 system이 있으면 instructions를 앞에 두고 `---`로 구분해 병합한다."""
        store = _FakeSkillStore(_skill_doc("지침서"))
        executor = CatalogNodeExecutor({"fake": _SystemNode}, skill_document_store=store)

        out = executor.execute(
            node=_node(parameters={"system": "원래 프롬프트"}, skill_id=uuid4()),
            config=_config("fake", category="ai"),
            inputs={},
            context=_ctx(),
        )

        assert out["seen_system"] == "지침서\n\n---\n\n원래 프롬프트"

    def test_skips_node_without_system_field(self):
        """ai 노드라도 system 필드가 없으면 주입 skip(store.load 미호출)."""
        store = _FakeSkillStore(_skill_doc())
        executor = CatalogNodeExecutor({"fake": _FakeNode}, skill_document_store=store)

        out = executor.execute(
            node=_node(skill_id=uuid4()),
            config=_config("fake", category="ai"),
            inputs={"value": 5},
            context=_ctx(),
        )

        assert out["echo"] == 5
        assert store.load_calls == []

    def test_skips_non_ai_node_with_system_field(self):
        """category!='ai'면 system 필드를 가졌어도 over-match 방지로 주입 skip (LOW #5)."""
        store = _FakeSkillStore(_skill_doc())
        executor = CatalogNodeExecutor({"fake": _SystemNode}, skill_document_store=store)

        out = executor.execute(
            node=_node(skill_id=uuid4()),
            config=_config("fake", category="transform"),
            inputs={"value": 6},
            context=_ctx(),
        )

        assert out["seen_system"] is None
        assert store.load_calls == []

    def test_no_skill_id_skips_load(self):
        """skill_id=None이면 store.load를 호출하지 않는다."""
        store = _FakeSkillStore(_skill_doc())
        executor = CatalogNodeExecutor({"fake": _SystemNode}, skill_document_store=store)

        out = executor.execute(
            node=_node(skill_id=None),
            config=_config("fake", category="ai"),
            inputs={"value": 2},
            context=_ctx(),
        )

        assert out["seen_system"] is None
        assert store.load_calls == []

    def test_missing_document_degrades(self):
        """load가 None(미존재)이면 무주입 degrade — 실행은 정상 진행."""
        store = _FakeSkillStore(document=None)
        executor = CatalogNodeExecutor({"fake": _SystemNode}, skill_document_store=store)

        out = executor.execute(
            node=_node(skill_id=uuid4()),
            config=_config("fake", category="ai"),
            inputs={"value": 3},
            context=_ctx(),
        )

        assert out["seen_system"] is None
        assert out["echo"] == 3

    def test_load_exception_degrades(self):
        """load가 예외를 던져도 무주입 degrade — 워크플로우 실행을 막지 않는다."""
        store = _FakeSkillStore(raises=True)
        executor = CatalogNodeExecutor({"fake": _SystemNode}, skill_document_store=store)

        out = executor.execute(
            node=_node(skill_id=uuid4()),
            config=_config("fake", category="ai"),
            inputs={"value": 4},
            context=_ctx(),
        )

        assert out["seen_system"] is None
        assert out["echo"] == 4

    def test_store_not_wired_degrades_without_raising(self):
        """store 미배선 + skill_id 있음 → degrade(credential과 달리 RuntimeError 금지)."""
        executor = CatalogNodeExecutor({"fake": _SystemNode})

        out = executor.execute(
            node=_node(skill_id=uuid4()),
            config=_config("fake", category="ai"),
            inputs={"value": 9},
            context=_ctx(),
        )

        assert out["seen_system"] is None
        assert out["echo"] == 9


# --- credential 복수화 (REQ-012) -----------------------------------------------

@dataclasses.dataclass
class _TokensOutput:
    tokens: dict


class _TokensNode:
    """process() 중 context.connection_tokens 스냅샷을 출력으로 반환(wipe 전 관측)."""

    input_schema = _FakeInput

    async def process(self, node_input: _FakeInput, context: NodeContext) -> _TokensOutput:
        return _TokensOutput(tokens=dict(context.connection_tokens))


class _MultiCredentialService:
    def __init__(self, captured: dict) -> None:
        self._captured = captured
        captured.setdefault("injected", [])

    async def inject(self, credential_id, node_id) -> PlaintextCredential:
        self._captured["injected"].append((credential_id, node_id))
        return PlaintextCredential(
            credential_id=str(credential_id), credential_kind="aes_gcm", value=f"tok-{credential_id}"
        )


def _multi_factory(captured: dict):
    @asynccontextmanager
    async def factory():
        yield _MultiCredentialService(captured)

    return factory


class TestCatalogNodeExecutorMultiCredential:
    def test_credential_ids_populate_connection_tokens(self):
        """credential_ids의 provider별로 inject → context.connection_tokens 적재 (REQ-012)."""
        captured: dict = {}
        slack, google = uuid4(), uuid4()
        executor = CatalogNodeExecutor(
            {"multi": _TokensNode}, credential_service_factory=_multi_factory(captured)
        )
        node = NodeInstance(
            instance_id=uuid4(), node_id=uuid4(), parameters={},
            credential_ids={"slack": slack, "google": google}, position=Position(x=0, y=0),
        )

        out = executor.execute(node=node, config=_config("multi"), inputs={}, context=_ctx())

        assert out["tokens"] == {"slack": f"tok-{slack}", "google": f"tok-{google}"}
        assert len(captured["injected"]) == 2

    def test_single_credential_ids_also_sets_primary_token(self):
        """단일 provider credential_ids면 connection_token(primary)도 채워 하위호환."""
        captured: dict = {}
        google = uuid4()
        executor = CatalogNodeExecutor(
            {"fake": _FakeNode}, credential_service_factory=_multi_factory(captured)
        )
        node = NodeInstance(
            instance_id=uuid4(), node_id=uuid4(), parameters={},
            credential_ids={"google": google}, position=Position(x=0, y=0),
        )

        out = executor.execute(node=node, config=_config("fake"), inputs={"value": 1}, context=_ctx())

        assert out["seen_token"] == f"tok-{google}"

    def test_connection_tokens_wiped_after_execution(self):
        """실행 종료 후 connection_tokens도 제거된다(평문 토큰 잔존 금지)."""
        captured: dict = {}
        ctx = _ctx()
        executor = CatalogNodeExecutor(
            {"multi": _TokensNode}, credential_service_factory=_multi_factory(captured)
        )
        node = NodeInstance(
            instance_id=uuid4(), node_id=uuid4(), parameters={},
            credential_ids={"slack": uuid4()}, position=Position(x=0, y=0),
        )

        executor.execute(node=node, config=_config("multi"), inputs={}, context=ctx)

        assert ctx.connection_tokens == {}
        assert ctx.connection_token is None
