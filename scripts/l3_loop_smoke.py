"""ADR-0023 L3 유한 순환 — L1+L2+L3 합성 end-to-end 로컬 스모크.

시나리오(ADR 예시): 시트읽기 → 요약 → 품질검증(condition) → 미통과면 재요약 루프 →
통과면 슬랙 전송. 실제 ``DispatchNodeUseCase`` + ``ReferenceResolver``(L1) +
``BranchEvaluator``(L2) + ``CyclicScheduler``(L3)를 가짜 executor로 구동한다.

검증:
  1. 품질게이트가 2회 retry 후 통과 → 요약 노드가 3회 실행(iteration 0/1/2).
  2. 슬랙 노드의 ``${요약.summary}``가 **마지막 iteration** 요약으로 해석(L1 latest-wins).
  3. 미통과 가지(루프 재진입)는 슬랙을 막지 않고, 통과 후에만 슬랙 실행(L2).

실행: services/execution_engine 에서
    ../../.venv/Scripts/python.exe ../../scripts/l3_loop_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

# execution_engine/src 를 import 경로에 추가 (스크립트 단독 실행용).
_EE = Path(__file__).resolve().parents[1] / "services" / "execution_engine"
sys.path.insert(0, str(_EE))

from common_schemas.enums import ExecutionStatus, RiskLevel  # noqa: E402
from common_schemas.workflow import (  # noqa: E402
    Edge,
    NodeConfig,
    NodeInstance,
    Position,
    WorkflowSchema,
)
from src.application.use_cases.dispatch_node import DispatchNodeUseCase  # noqa: E402
from src.application.use_cases.execute_workflow import ExecuteWorkflowUseCase  # noqa: E402
from src.domain.entities.execution_context import ExecutionContext  # noqa: E402
from src.domain.ports.event_publisher_port import EventPublisherPort  # noqa: E402
from src.domain.services.execution_orchestrator import ExecutionOrchestrator  # noqa: E402
from src.domain.services.retry_manager import RetryManager  # noqa: E402
from src.domain.services.topological_scheduler import TopologicalScheduler  # noqa: E402

PASS_AFTER = 2  # 가짜 품질게이트: 2회 retry 후 통과


def _node(node_id, params=None):
    return NodeInstance(
        instance_id=uuid4(), node_id=node_id,
        parameters=params or {}, position=Position(x=0, y=0),
    )


def _cfg(node_id, name, category):
    return NodeConfig(
        node_id=node_id, node_type=name, name=name, category=category, version="1",
        input_schema={}, output_schema={}, parameter_schema={},
        risk_level=RiskLevel.LOW, required_connections=[], description="", is_mvp=True,
    )


class _FakeExecutor:
    """노드 타입별로 출력을 시뮬레이션. 품질게이트는 호출 횟수로 통과/재시도 결정."""

    def __init__(self, configs_by_id):
        self._configs = configs_by_id
        self._gate_calls = 0
        self._summarize_calls = 0

    def execute(self, node, config, inputs, context):
        cat = config.category
        name = config.name
        if name == "read_sheet":
            return {"rows": "row1,row2,row3"}
        if name == "summarize":
            self._summarize_calls += 1
            # L1: 입력 text 는 ${read.rows} 가 해석된 값이어야 한다.
            assert node.parameters.get("text") == "row1,row2,row3", node.parameters
            return {"summary": f"summary-v{self._summarize_calls}"}
        if cat == "condition":  # 품질게이트
            self._gate_calls += 1
            if self._gate_calls <= PASS_AFTER:
                return {"branch": "retry", "score": 0.4}
            return {"branch": "pass", "score": 0.95}
        if name == "slack":
            # L1: ${요약.summary} 가 마지막 iteration 요약으로 해석돼야 한다.
            return {"sent": True, "delivered_text": node.parameters.get("message")}
        return {}


class _Events(EventPublisherPort):
    def publish_status(self, execution_id, status):
        pass

    def publish_node_complete(self, execution_id, node_result):
        pass


class _WorkflowRepo:
    def __init__(self, workflow, configs_by_id):
        self._wf = workflow
        self._configs = configs_by_id

    def get(self, workflow_id):
        return self._wf

    def get_node_config(self, node_id):
        return self._configs[node_id]


class _ExecRepo:
    def save(self, result):
        pass


def main() -> int:
    read_id, sum_id, gate_id, slack_id = uuid4(), uuid4(), uuid4(), uuid4()
    configs = {
        read_id: _cfg(read_id, "read_sheet", "action"),
        sum_id: _cfg(sum_id, "summarize", "transform"),
        gate_id: _cfg(gate_id, "quality_gate", "condition"),
        slack_id: _cfg(slack_id, "slack", "action"),
    }
    # ${ref} 는 instance_id 로 해석된다(L1). node_id 가 아님에 주의.
    read = _node(read_id)
    summarize = _node(sum_id, {"text": f"${{{read.instance_id}.rows}}"})
    gate = _node(gate_id, {"max_iterations": 5})
    slack = _node(slack_id, {"message": f"${{{summarize.instance_id}.summary}}"})

    # read → summarize → gate ; gate --retry--> summarize, gate --pass--> slack
    wf = WorkflowSchema(
        workflow_id=uuid4(), name="quality-gate-loop", scope="private", is_draft=False,
        nodes=[read, summarize, gate, slack],
        connections=[
            Edge(from_instance_id=read.instance_id, to_instance_id=summarize.instance_id,
                 from_handle="output", to_handle="input"),
            Edge(from_instance_id=summarize.instance_id, to_instance_id=gate.instance_id,
                 from_handle="output", to_handle="input"),
            Edge(from_instance_id=gate.instance_id, to_instance_id=summarize.instance_id,
                 from_handle="retry", to_handle="input"),
            Edge(from_instance_id=gate.instance_id, to_instance_id=slack.instance_id,
                 from_handle="pass", to_handle="input"),
        ],
    )

    executor = _FakeExecutor(configs)
    use_case = ExecuteWorkflowUseCase(
        workflow_repo=_WorkflowRepo(wf, configs),
        execution_repo=_ExecRepo(),
        orchestrator=ExecutionOrchestrator(TopologicalScheduler()),
        dispatch_node=DispatchNodeUseCase(executor, _Events(), RetryManager()),
        event_publisher=_Events(),
    )
    ctx = ExecutionContext(
        execution_id=uuid4(), workflow_id=wf.workflow_id, user_id=uuid4(), trigger_type="manual",
    )

    result = use_case.execute(wf.workflow_id, ctx)

    ok = True
    by = lambda nid: [r for r in result.node_results if r.node_instance_id == nid]  # noqa: E731

    def check(label, cond):
        nonlocal ok
        ok = ok and cond
        print(f"  [{'OK' if cond else 'FAIL'}] {label}")

    print(f"status={result.status.value} nodes={len(result.node_results)} error={result.error}")
    check("실행 완료(COMPLETED)", result.status == ExecutionStatus.COMPLETED)
    sum_results = sorted(by(summarize.instance_id), key=lambda r: r.iteration)
    check("요약 3회 실행(iteration 0/1/2)", [r.iteration for r in sum_results] == [0, 1, 2])
    check("품질게이트 3회 실행", len(by(gate.instance_id)) == 3)
    slack_results = by(slack.instance_id)
    check("슬랙 1회 실행(통과 후)", len(slack_results) == 1 and slack_results[0].status == "succeeded")
    check(
        "슬랙이 마지막 iteration 요약 수신(L1 latest-wins)",
        bool(slack_results) and slack_results[0].output.get("delivered_text") == "summary-v3",
    )

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
