from __future__ import annotations

from uuid import UUID

from common_schemas.enums import ExecutionStatus

from ...domain.entities.execution_context import ExecutionContext
from ...domain.entities.execution_result import ExecutionResult, NodeResult
from ...domain.ports.event_publisher_port import EventPublisherPort
from ...domain.ports.execution_repository_port import ExecutionRepositoryPort
from ...domain.ports.workflow_repository_port import WorkflowRepositoryPort
from ...domain.services.execution_orchestrator import ExecutionOrchestrator
from .dispatch_node import DispatchNodeUseCase


class ExecuteWorkflowUseCase:

    def __init__(
        self,
        workflow_repo: WorkflowRepositoryPort,
        execution_repo: ExecutionRepositoryPort,
        orchestrator: ExecutionOrchestrator,
        dispatch_node: DispatchNodeUseCase,
        event_publisher: EventPublisherPort,
    ) -> None:
        self._workflow_repo = workflow_repo
        self._execution_repo = execution_repo
        self._orchestrator = orchestrator
        self._dispatch_node = dispatch_node
        self._events = event_publisher

    def execute(self, workflow_id: UUID, context: ExecutionContext) -> ExecutionResult:
        result = ExecutionResult(
            execution_id=context.execution_id,
            workflow_id=workflow_id,
            user_id=context.user_id,
            started_at=context.started_at,
        )

        try:
            workflow = self._workflow_repo.get(workflow_id)
            levels = self._orchestrator.plan(workflow)

            self._events.publish_status(context.execution_id, ExecutionStatus.RUNNING)

            for level in levels:
                level_results = self._execute_level(level, workflow_id, context)
                result.node_results.extend(level_results)

                if self._orchestrator.has_failures(level_results):
                    result.mark_failed(
                        f"레벨 {level.level}에서 "
                        f"{sum(1 for r in level_results if r.status == 'failed')}개 노드 실패"
                    )
                    break

            if result.status == ExecutionStatus.RUNNING:
                result.mark_completed()

        except Exception as e:
            result.mark_failed(str(e))

        self._execution_repo.save(result)
        self._events.publish_status(context.execution_id, result.status)
        return result

    def _execute_level(self, level, workflow_id, context):
        node_results: list[NodeResult] = []
        for node in level.nodes:
            config = self._workflow_repo.get_node_config(node.node_id)
            node_result = self._dispatch_node.execute(
                node=node,
                config=config,
                inputs=context.parameters,
                user_id=context.user_id,
                execution_id=context.execution_id,
            )
            self._events.publish_node_complete(context.execution_id, node_result)
            node_results.append(node_result)
        return node_results
