from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from uuid import UUID

from common_schemas.enums import ExecutionStatus

from ...domain.entities.execution_context import ExecutionContext
from ...domain.entities.execution_level import ExecutionLevel
from ...domain.entities.execution_result import ExecutionResult, NodeResult
from ...domain.ports.event_publisher_port import EventPublisherPort
from ...domain.ports.execution_repository_port import ExecutionRepositoryPort
from ...domain.ports.workflow_repository_port import WorkflowRepositoryPort
from ...domain.services.execution_orchestrator import ExecutionOrchestrator
from ...domain.services.reference_resolver import ReferenceResolver
from .dispatch_node import DispatchNodeUseCase


class ExecuteWorkflowUseCase:

    def __init__(
        self,
        workflow_repo: WorkflowRepositoryPort,
        execution_repo: ExecutionRepositoryPort,
        orchestrator: ExecutionOrchestrator,
        dispatch_node: DispatchNodeUseCase,
        event_publisher: EventPublisherPort,
        reference_resolver: ReferenceResolver | None = None,
    ) -> None:
        self._workflow_repo = workflow_repo
        self._execution_repo = execution_repo
        self._orchestrator = orchestrator
        self._dispatch_node = dispatch_node
        self._events = event_publisher
        self._resolver = reference_resolver or ReferenceResolver()

    def execute(self, workflow_id: UUID, context: ExecutionContext) -> ExecutionResult:
        result = ExecutionResult(
            execution_id=context.execution_id,
            workflow_id=workflow_id,
            user_id=context.user_id,
            started_at=context.started_at,
            task_queue_id=context.task_queue_id,
        )

        try:
            workflow = self._workflow_repo.get(workflow_id)
            levels = self._orchestrator.plan(workflow)

            self._events.publish_status(context.execution_id, ExecutionStatus.RUNNING)

            # 상류 노드 출력 누적 — 하류 노드 파라미터의 ${ref} 해석 소스 (ADR-0023 L1).
            # 같은 레벨 노드는 서로 독립(위상정렬)이라, 레벨 *완료 후* 일괄 병합한다.
            node_outputs: dict[str, dict[str, Any]] = {}

            for level in levels:
                level_results = self._execute_level(level, workflow_id, context, node_outputs)
                result.node_results.extend(level_results)
                for r in level_results:
                    if r.status == "succeeded" and isinstance(r.output, dict):
                        node_outputs[str(r.node_instance_id)] = r.output

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

    def _execute_level(
        self,
        level: ExecutionLevel,
        workflow_id: UUID,
        context: ExecutionContext,
        node_outputs: dict[str, dict[str, Any]],
    ) -> list[NodeResult]:
        if len(level.nodes) == 1:
            return [self._dispatch_single(level.nodes[0], context, node_outputs)]

        node_results: list[NodeResult] = []
        with ThreadPoolExecutor(max_workers=len(level.nodes)) as pool:
            futures = {
                pool.submit(self._dispatch_single, node, context, node_outputs): node
                for node in level.nodes
            }
            for future in as_completed(futures):
                node_results.append(future.result())

        return node_results

    def _dispatch_single(
        self, node, context: ExecutionContext, node_outputs: dict[str, dict[str, Any]],
    ) -> NodeResult:
        config = self._workflow_repo.get_node_config(node.node_id)
        # 노드 파라미터의 ${상류.출력} 참조를 해석한 노드로 교체 후 dispatch (ADR-0023 L1).
        # model_copy로 resolved 파라미터만 갈아끼워 기존 입력 precedence(global override)는 보존.
        resolved_params = self._resolver.resolve_params(node.parameters, node_outputs)
        resolved_node = node.model_copy(update={"parameters": resolved_params})
        node_result = self._dispatch_node.execute(
            node=resolved_node,
            config=config,
            inputs=context.parameters,
            user_id=context.user_id,
            execution_id=context.execution_id,
        )
        self._events.publish_node_complete(context.execution_id, node_result)
        return node_result
