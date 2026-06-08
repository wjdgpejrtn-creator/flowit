"""파리티 가드 — branch_on_classification 모티프 ↔ 엔진 BranchEvaluator/GraphValidator.

§6.1 모티프 라이브러리: composer가 `branch_on_classification`을 그라운딩하면 drafter는
`router -[true]-> path_A`, `router -[false]-> path_B`로 배선한다(drafter `_motif_block`).
이 핸들 컨벤션이 엔진 `BranchEvaluator`가 실제로 라우팅하는 selector와 어긋나면,
composer가 통과시킨 분기 draft가 런타임에 **전 갈래 live로 degrade**(XOR 깨짐)된다 —
false accept. 본 테스트는 두 가지를 박는다:

  1. drafter가 쓰는 핸들("true"/"false")이 if_condition 출력 selector와 일치해
     BranchEvaluator가 **정확히 한 갈래만** live로 고른다(degrade-all 아님).
  2. 분기(condition 다중 outgoing, 무순환) 워크플로우를 GraphValidator가 **순환으로
     거부하지 않는다**(분기는 DAG — CyclicScheduler 계약과 정합).

조립 계층(execution_engine)에 두는 이유: nodes_graph(validator)와 execution_engine
(BranchEvaluator)를 동시에 import할 수 있는 유일한 지점이기 때문.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas.enums import ErrorCode, RiskLevel
from common_schemas.workflow import Edge, NodeInstance, Position, WorkflowSchema
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.services.graph_validator import GraphValidator
from src.domain.services.branch_evaluator import BranchEvaluator

# drafter `_motif_block`의 branch 배선이 쓰는 핸들(코드와 1:1 — 바뀌면 본 테스트가 깨져야 함).
_BRANCH_HANDLES = ["true", "false"]
# if_condition 출력 selector(BranchEvaluator 실측: if_condition → "branch" 필드).
_IF_CONDITION_OUTPUT = {"branch": "true", "value": {"any": "passthrough"}}


def test_branch_handles_route_exactly_one_path():
    """모티프 핸들이 if_condition selector와 일치 → 정확히 한 갈래만 live(degrade-all 아님)."""
    ev = BranchEvaluator()
    live = ev.live_handles(_IF_CONDITION_OUTPUT, _BRANCH_HANDLES)
    assert live == {"true"}, "모티프 'true' 핸들이 if_condition selector와 어긋남 → XOR degrade"
    assert ev.is_edge_live(True, _IF_CONDITION_OUTPUT, _BRANCH_HANDLES, "true") is True
    assert ev.is_edge_live(True, _IF_CONDITION_OUTPUT, _BRANCH_HANDLES, "false") is False


class _InMemoryRepo:
    def __init__(self):
        self._store = {}

    async def upsert(self, d):
        self._store[str(d.node_id)] = d
        return d

    async def list_all(self, mvp_only=False):
        return list(self._store.values())

    async def get_by_id(self, node_id):
        return self._store.get(str(node_id))

    async def search_by_embedding(self, q, limit=10):
        return list(self._store.values())[:limit]


def _def(node_id, category: str) -> NodeDefinition:
    return NodeDefinition(
        node_id=node_id, node_type="x", name="x", category=category, version="1.0.0",
        input_schema={}, output_schema={}, parameter_schema={},
        risk_level=RiskLevel.LOW, required_connections=[], description="x", is_mvp=True,
    )


@pytest.mark.asyncio
async def test_branch_workflow_not_rejected_as_cycle():
    """XOR 분기(condition 다중 outgoing, 무순환)는 validator가 순환으로 거부하지 않는다.

    classifier(ai) → router(condition) -[true]-> A, -[false]-> B.
    """
    repo = _InMemoryRepo()
    cats = ["ai", "condition", "action", "action"]  # classifier, router, path_A, path_B
    instances = []
    for cat in cats:
        node_id = uuid4()
        await repo.upsert(_def(node_id, cat))
        instances.append(
            NodeInstance(instance_id=uuid4(), node_id=node_id, parameters={},
                         position=Position(x=0, y=0))
        )
    edge_spec = [(0, 1, "output"), (1, 2, "true"), (1, 3, "false")]
    edges = [
        Edge(from_instance_id=instances[i].instance_id, to_instance_id=instances[j].instance_id,
             from_handle=fh, to_handle="input")
        for (i, j, fh) in edge_spec
    ]
    wf = WorkflowSchema(
        workflow_id=uuid4(), name="wf", scope="private", is_draft=False,
        nodes=instances, connections=edges,
    )

    result = await GraphValidator(repo).validate(wf)
    assert not any(e.code == ErrorCode.E_CYCLE_DETECTED for e in result.errors), (
        "분기 워크플로우가 순환으로 오거부됨 — CyclicScheduler 계약과 drift"
    )
