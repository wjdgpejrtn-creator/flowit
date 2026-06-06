"""파리티 가드 — GraphValidator(nodes_graph) ↔ CyclicScheduler(execution_engine).

같은 순환 수용 계약(non-trivial SCC는 condition 노드 ≥1개면 허용, 없으면
E_CYCLE_DETECTED)을 두 모듈이 **독립 2구현**한다 — 의존 방향(services→modules,
역 import 금지)상 `_tarjan_sccs`/`_is_nontrivial`/condition 판정을 공유할 수 없기
때문이다. 한쪽이 기준을 바꾸면 draft가 *validator 통과 → 엔진 거부*(또는 역)로
갈린다. 본 테스트는 동일 워크플로우 코퍼스에서 양쪽 판정이 일치함을 보장하는
조립-계층 파리티 가드다 (PR #392 리뷰 MED fast-follow).

조립 계층(execution_engine)에 두는 이유: 두 모듈을 동시에 import할 수 있는 유일한
지점이기 때문 (nodes_graph 유닛은 CyclicScheduler를 import 불가).
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas.enums import ErrorCode, RiskLevel
from common_schemas.exceptions import ValidationError
from common_schemas.workflow import Edge, NodeInstance, Position, WorkflowSchema
from nodes_graph.domain.entities.node_definition import NodeDefinition
from nodes_graph.domain.services.graph_validator import GraphValidator
from src.domain.services.cyclic_scheduler import CyclicScheduler


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


def _def(category):
    return NodeDefinition(
        node_id=uuid4(), node_type="x", name="x", category=category, version="1.0.0",
        input_schema={}, output_schema={}, parameter_schema={},
        risk_level=RiskLevel.LOW, required_connections=[], description="x", is_mvp=True,
    )


async def _build(is_condition_flags, edge_pairs):
    """is_condition_flags: list[bool] — 각 노드의 condition 여부 (단일 SSOT).
    edge_pairs: list[(i, j, from_handle)].
    validator용 repo(category)와 scheduler용 is_brancher를 같은 출처에서 만든다."""
    repo = _InMemoryRepo()
    instances = []
    is_brancher = {}
    for is_cond in is_condition_flags:
        d = _def("condition" if is_cond else "action")
        await repo.upsert(d)
        ni = NodeInstance(
            instance_id=uuid4(), node_id=d.node_id, parameters={}, position=Position(x=0, y=0)
        )
        instances.append(ni)
        is_brancher[ni.instance_id] = is_cond
    edges = [
        Edge(
            from_instance_id=instances[i].instance_id,
            to_instance_id=instances[j].instance_id,
            from_handle=fh, to_handle="input",
        )
        for (i, j, fh) in edge_pairs
    ]
    wf = WorkflowSchema(
        workflow_id=uuid4(), name="wf", scope="private", is_draft=False,
        nodes=instances, connections=edges,
    )
    return wf, is_brancher, repo


# (label, is_condition flags, edges (i,j,from_handle), 순환거부 기대)
_CORPUS = [
    ("pure_dag", [False, False, False], [(0, 1, "output"), (1, 2, "output")], False),
    ("loop_with_condition", [False, True], [(0, 1, "output"), (1, 0, "retry")], False),
    ("loop_without_condition", [False, False], [(0, 1, "output"), (1, 0, "output")], True),
    ("condition_self_loop", [True, False], [(0, 0, "retry"), (0, 1, "done")], False),
    ("noncondition_self_loop", [False, False], [(0, 0, "x"), (0, 1, "output")], True),
    (
        "escapable_loop_E_S_C_X", [False, False, True, False],
        [(0, 1, "output"), (1, 2, "output"), (2, 1, "retry"), (2, 3, "done")], False,
    ),
    (
        "two_sccs_one_unbreakable", [False, True, False, False],
        [(0, 1, "output"), (1, 0, "retry"), (1, 2, "output"), (2, 3, "output"), (3, 2, "output")],
        True,
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,conds,edges,expect_rejected", _CORPUS, ids=[c[0] for c in _CORPUS]
)
async def test_validator_scheduler_cycle_parity(label, conds, edges, expect_rejected):
    wf, is_brancher, repo = await _build(conds, edges)

    result = await GraphValidator(repo).validate(wf)
    validator_rejects = any(e.code == ErrorCode.E_CYCLE_DETECTED for e in result.errors)

    scheduler_rejects = False
    try:
        CyclicScheduler().plan(wf, is_brancher)
    except ValidationError as exc:
        scheduler_rejects = exc.code == ErrorCode.E_CYCLE_DETECTED

    # 파리티: 두 모듈 판정이 서로 일치 + 기대값과 일치
    assert validator_rejects == scheduler_rejects, (
        f"{label}: validator={validator_rejects} ≠ scheduler={scheduler_rejects} — 수용 계약 drift"
    )
    assert validator_rejects == expect_rejected
