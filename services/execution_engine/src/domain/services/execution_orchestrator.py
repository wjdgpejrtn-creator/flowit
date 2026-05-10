from __future__ import annotations

from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import ExecutionError
from common_schemas.workflow import WorkflowSchema

from ..entities.execution_level import ExecutionLevel
from ..entities.execution_result import NodeResult
from .topological_scheduler import TopologicalScheduler

VALID_TRANSITIONS: dict[ExecutionStatus, set[ExecutionStatus]] = {
    ExecutionStatus.RUNNING: {
        ExecutionStatus.PAUSED,
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
    },
    ExecutionStatus.PAUSED: {ExecutionStatus.RUNNING},
}


class ExecutionOrchestrator:
    """레벨별 순차 실행, 레벨 내 병렬 실행 오케스트레이션 규칙.

    순수 비즈니스 규칙만 캡슐화한다 (Port/Repository 의존 없음).
    """

    def __init__(self, scheduler: TopologicalScheduler) -> None:
        self._scheduler = scheduler

    def plan(self, workflow: WorkflowSchema) -> list[ExecutionLevel]:
        if not workflow.validate_graph():
            raise ExecutionError(
                "워크플로우 그래프가 유효하지 않습니다",
                code="E_INVALID_GRAPH",
            )
        self._scheduler.validate_dag(workflow)
        return self._scheduler.schedule(workflow)

    def has_failures(self, level_results: list[NodeResult]) -> bool:
        return any(r.status == "failed" for r in level_results)

    def validate_state_transition(
        self, current: ExecutionStatus, target: ExecutionStatus,
    ) -> None:
        allowed = VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ExecutionError(
                f"Cannot transition from {current.value} to {target.value}",
                code="E_INVALID_STATE_TRANSITION",
            )
