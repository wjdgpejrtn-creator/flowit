"""CatalogNodeExecutor 단위 테스트 — node_type 조회 → BaseNode.process() 실행 (ADR-0018)."""
from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas import NodeContext
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
        """input_schema에 없는 키(예: credential 주입 잔여 __user_id__)는 무시."""
        out = executor.execute(
            node=_node(),
            config=_config("if_condition"),
            inputs={"left": 5, "operator": "eq", "right": 5, "__user_id__": "x"},
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

    def test_external_stub_raises_not_implemented(self, executor):
        """external 25종은 Phase 1에서 NotImplementedError 스텁 — 예외가 그대로 전파."""
        with pytest.raises(NotImplementedError):
            executor.execute(
                node=_node(),
                config=_config("rest_api"),
                inputs={"base_url": "https://example.com"},
                context=_ctx(),
            )
