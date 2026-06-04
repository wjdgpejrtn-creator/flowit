from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from common_schemas.enums import ExecutionStatus
from common_schemas.workflow import Edge

from ...domain.entities.execution_context import ExecutionContext
from ...domain.entities.execution_level import ExecutionLevel
from ...domain.entities.execution_result import ExecutionResult, NodeResult
from ...domain.ports.event_publisher_port import EventPublisherPort
from ...domain.ports.execution_repository_port import ExecutionRepositoryPort
from ...domain.ports.workflow_repository_port import WorkflowRepositoryPort
from ...domain.services.branch_evaluator import BranchEvaluator
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
        branch_evaluator: BranchEvaluator | None = None,
    ) -> None:
        self._workflow_repo = workflow_repo
        self._execution_repo = execution_repo
        self._orchestrator = orchestrator
        self._dispatch_node = dispatch_node
        self._events = event_publisher
        self._resolver = reference_resolver or ReferenceResolver()
        self._branch = branch_evaluator or BranchEvaluator()

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

            # config 캐시 + 조건 노드 판별 + 엣지 인접 (ADR-0023 L2 reachability).
            configs = {
                n.node_id: self._workflow_repo.get_node_config(n.node_id) for n in workflow.nodes
            }
            is_brancher = {
                n.instance_id: getattr(configs.get(n.node_id), "category", None) == "condition"
                for n in workflow.nodes
            }
            incoming: dict[UUID, list[Edge]] = defaultdict(list)
            outgoing_handles: dict[UUID, list[str]] = defaultdict(list)
            for e in workflow.connections:
                incoming[e.to_instance_id].append(e)
                outgoing_handles[e.from_instance_id].append(e.from_handle)

            # 상류 노드 출력 누적 — 하류 노드 파라미터의 ${ref} 해석 소스 (ADR-0023 L1).
            # 같은 레벨 노드는 서로 독립(위상정렬)이라, 레벨 *완료 후* 일괄 병합한다.
            node_outputs: dict[str, dict[str, Any]] = {}
            # 노드 도달 가능 여부 (ADR-0023 L2). 위상정렬상 선행이 먼저 확정된다.
            reachable: dict[UUID, bool] = {}

            for level in levels:
                level_results = self._execute_level(
                    level, context, configs, node_outputs, reachable, incoming,
                    outgoing_handles, is_brancher,
                )
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
        context: ExecutionContext,
        configs: dict[UUID, Any],
        node_outputs: dict[str, dict[str, Any]],
        reachable: dict[UUID, bool],
        incoming: dict[UUID, list[Edge]],
        outgoing_handles: dict[UUID, list[str]],
        is_brancher: dict[UUID, bool],
    ) -> list[NodeResult]:
        # 도달 가능 노드만 실행, 나머지는 skip (ADR-0023 L2 — 안 탄 분기 가지 차단).
        results: list[NodeResult] = []
        to_run = []
        for node in level.nodes:
            if self._is_reachable(node, incoming, outgoing_handles, reachable, node_outputs, is_brancher):
                reachable[node.instance_id] = True
                to_run.append(node)
            else:
                reachable[node.instance_id] = False
                skipped = self._skipped_result(node)
                self._events.publish_node_complete(context.execution_id, skipped)
                results.append(skipped)

        if len(to_run) == 1:
            results.append(self._dispatch_single(to_run[0], context, configs, node_outputs))
        elif to_run:
            with ThreadPoolExecutor(max_workers=len(to_run)) as pool:
                futures = {
                    pool.submit(self._dispatch_single, node, context, configs, node_outputs): node
                    for node in to_run
                }
                for future in as_completed(futures):
                    results.append(future.result())

        return results

    def _is_reachable(
        self,
        node,
        incoming: dict[UUID, list[Edge]],
        outgoing_handles: dict[UUID, list[str]],
        reachable: dict[UUID, bool],
        node_outputs: dict[str, dict[str, Any]],
        is_brancher: dict[UUID, bool],
    ) -> bool:
        inc = incoming.get(node.instance_id, [])
        if not inc:
            return True  # 루트 노드는 항상 실행
        for e in inc:
            src = e.from_instance_id
            if not reachable.get(src, False):
                continue  # 선행이 미도달/skip
            src_out = node_outputs.get(str(src))
            if src_out is None:
                continue  # 선행이 성공 출력 없음(실패 등)
            if self._branch.is_edge_live(
                is_brancher.get(src, False), src_out, outgoing_handles.get(src, []), e.from_handle
            ):
                return True
        return False

    @staticmethod
    def _skipped_result(node) -> NodeResult:
        now = datetime.now(UTC)
        return NodeResult(
            node_instance_id=node.instance_id,
            status="skipped",
            output={},
            started_at=now,
            completed_at=now,
        )

    def _dispatch_single(
        self, node, context: ExecutionContext, configs: dict[UUID, Any],
        node_outputs: dict[str, dict[str, Any]],
    ) -> NodeResult:
        config = configs[node.node_id]
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
