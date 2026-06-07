from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import NotFoundError
from common_schemas.workflow import Edge

from ...domain.entities.execution_context import ExecutionContext
from ...domain.entities.execution_level import ExecutionLevel
from ...domain.entities.execution_result import ExecutionResult, NodeResult
from ...domain.entities.execution_step import LoopBody
from ...domain.ports.event_publisher_port import EventPublisherPort
from ...domain.ports.execution_repository_port import ExecutionRepositoryPort
from ...domain.ports.workflow_repository_port import WorkflowRepositoryPort
from ...domain.services.branch_evaluator import BranchEvaluator
from ...domain.services.cyclic_scheduler import CyclicScheduler
from ...domain.services.execution_orchestrator import ExecutionOrchestrator
from ...domain.services.reference_resolver import ReferenceResolver
from .dispatch_node import DispatchNodeUseCase


@dataclass
class _Checkpoint:
    """resume 시 복원하는 직전 실행 상태 (ADR-0025 체크포인트 재개).

    step 경계에서만 pause하므로 step은 원자적으로 완료된다 — 따라서 저장된
    node_results는 "완전히 끝난 step"의 결과만 담긴다. 부분 완료 step은 없다.
    """

    results: list[NodeResult] = field(default_factory=list)
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    reachable: dict[UUID, bool] = field(default_factory=dict)
    completed_ids: set[UUID] = field(default_factory=set)


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
        cyclic_scheduler: CyclicScheduler | None = None,
    ) -> None:
        self._workflow_repo = workflow_repo
        self._execution_repo = execution_repo
        self._orchestrator = orchestrator
        self._dispatch_node = dispatch_node
        self._events = event_publisher
        self._resolver = reference_resolver or ReferenceResolver()
        self._branch = branch_evaluator or BranchEvaluator()
        self._planner = cyclic_scheduler or CyclicScheduler()

    def execute(self, workflow_id: UUID, context: ExecutionContext) -> ExecutionResult:
        result = ExecutionResult(
            execution_id=context.execution_id,
            workflow_id=workflow_id,
            user_id=context.user_id,
            started_at=context.started_at,
            task_queue_id=context.task_queue_id,
        )

        # resume 트리거면 직전 실행의 완료 노드를 복원한다 — 성공 노드는 재디스패치하지
        # 않고 하류 ${ref}/reachability 컨텍스트만 시드한다 (ADR-0025 체크포인트 재개).
        checkpoint = (
            self._load_checkpoint(context.execution_id)
            if context.trigger_type == "resume"
            else None
        )

        try:
            workflow = self._workflow_repo.get(workflow_id)

            # config 캐시 + 조건 노드 판별 + 엣지 인접 (ADR-0023 L2 reachability).
            configs = {
                n.node_id: self._workflow_repo.get_node_config(n.node_id) for n in workflow.nodes
            }
            is_brancher = {
                n.instance_id: getattr(configs.get(n.node_id), "category", None) == "condition"
                for n in workflow.nodes
            }
            outgoing_handles: dict[UUID, list[str]] = defaultdict(list)
            for e in workflow.connections:
                outgoing_handles[e.from_instance_id].append(e.from_handle)

            # 응축 DAG 스텝 — 비순환은 레벨, 순환은 루프 바디 (ADR-0023 L3).
            steps = self._planner.plan(workflow, is_brancher)

            # reachability용 incoming은 back-edge를 제외한다 — back-edge는 루프 내부 제어
            # 엣지라 진입/하류 도달 판정에 끼면 루프 루트(외부 선행 없는 진입 노드)를 막는다.
            # 루프 지속 판정(_loop_continues)은 outgoing_handles 풀셋을 그대로 쓴다.
            back_set = {e for st in steps if st.kind == "loop" for e in st.loop.back_edges}
            incoming: dict[UUID, list[Edge]] = defaultdict(list)
            for e in workflow.connections:
                if e not in back_set:
                    incoming[e.to_instance_id].append(e)

            self._events.publish_status(context.execution_id, ExecutionStatus.RUNNING)

            # 상류 노드 출력 누적 — 하류 ${ref} 해석 소스 (L1, latest-wins).
            node_outputs: dict[str, dict[str, Any]] = {}
            # 노드 도달 가능 여부 (L2). 위상정렬상 선행이 먼저 확정된다.
            reachable: dict[UUID, bool] = {}
            # 가드 초과로 강제 탈출한 루프의 exit 엣지 — 하류 reachability에서 강제 live (L3).
            forced_live: set[Edge] = set()
            # 이미 완료된(succeeded/skipped) 노드 — resume 시 재디스패치 skip 판정용.
            completed_ids: set[UUID] = set()

            if checkpoint is not None:
                result.node_results.extend(checkpoint.results)
                node_outputs.update(checkpoint.node_outputs)
                reachable.update(checkpoint.reachable)
                completed_ids = checkpoint.completed_ids
                for nr in checkpoint.results:
                    self._events.publish_node_complete(context.execution_id, nr)

            # 실행 시작 시점에 RUNNING row를 영속화한다 — 폴링/pause 조회/협조적 재확인의
            # 전제. (직전엔 종료 시점에만 save해 실행 중 row가 없어 pause가 불가능했다.)
            result.status = ExecutionStatus.RUNNING
            self._execution_repo.save(result)

            for step in steps:
                # 협조적 pause — step 경계에서 DB status를 재조회해 PAUSED면 부분 결과를
                # 보존한 채 중단한다 (완료/실패 마킹 없이). 다음 step 진입 전에만 체크하므로
                # step은 원자적으로 끝난다(부분 완료 step 없음 → 체크포인트 granularity=step).
                if self._is_pause_requested(context.execution_id):
                    result.status = ExecutionStatus.PAUSED
                    break

                # resume: 이미 완전히 끝난 step은 재실행하지 않는다. 위 시드로 하류
                # 컨텍스트(node_outputs/reachable)는 이미 복원돼 있다.
                step_ids = self._step_node_ids(step)
                if completed_ids and step_ids and all(nid in completed_ids for nid in step_ids):
                    continue

                if step.kind == "level":
                    level_results = self._execute_level(
                        step.level, context, configs, node_outputs, reachable,
                        incoming, outgoing_handles, is_brancher, forced_live,
                    )
                    result.node_results.extend(level_results)
                    if self._orchestrator.has_failures(level_results):
                        result.mark_failed(
                            f"레벨 {step.level.level}에서 "
                            f"{sum(1 for r in level_results if r.status == 'failed')}개 노드 실패"
                        )
                        break
                else:
                    loop_results, failed = self._execute_loop(
                        step.loop, context, configs, node_outputs, reachable,
                        incoming, outgoing_handles, is_brancher, forced_live,
                    )
                    result.node_results.extend(loop_results)
                    if failed:
                        result.mark_failed("루프 바디에서 노드 실패")
                        break

                # step 완료마다 부분 결과를 체크포인트로 저장 — 폴링 진행률 노출 +
                # pause/crash 시 resume이 끝난 step부터 이어가게 한다. status는 쓰지
                # 않는다(save_checkpoint) — 협조적 pause가 쓴 PAUSED를 덮어쓰지 않기 위함.
                self._execution_repo.save_checkpoint(result)

            # 마지막 step 실행 도중 도착한 pause는 위 top-check가 못 잡는다(다음 step 없음).
            # 루프 종료 후 한 번 더 재확인해 PAUSED면 완료로 마킹하지 않는다.
            if result.status == ExecutionStatus.RUNNING and self._is_pause_requested(
                context.execution_id
            ):
                result.status = ExecutionStatus.PAUSED

            if result.status == ExecutionStatus.RUNNING:
                result.mark_completed()

        except Exception as e:
            result.mark_failed(str(e))

        self._execution_repo.save(result)
        self._events.publish_status(context.execution_id, result.status)
        return result

    def _load_checkpoint(self, execution_id: UUID) -> _Checkpoint | None:
        """직전 실행의 node_results에서 완료 노드를 복원한다 (resume 전용).

        row이 아직 없으면(최초 실행이 save 전이었거나 미존재) None — 체크포인트 없이
        처음부터 실행한다. 일시적 DB 오류·역직렬화 실패 등은 **삼키지 않고 전파**한다 —
        조용히 None을 반환하면 resume이 완료 노드를 전부 재실행해 외부 부작용(Slack/시트
        등)을 중복시키므로(이 PR의 존재 이유를 무력화), 차라리 task를 실패시켜 PAUSED를
        유지하고 사용자가 재시도하게 한다 (ADR-0025, #380 리뷰 MED).
        """
        try:
            prior = self._execution_repo.get(execution_id)
        except NotFoundError:
            return None
        cp = _Checkpoint()
        for nr in getattr(prior, "node_results", []):
            if nr.status not in ("succeeded", "skipped"):
                continue
            cp.results.append(nr)
            cp.completed_ids.add(nr.node_instance_id)
            cp.reachable[nr.node_instance_id] = nr.status == "succeeded"
            if nr.status == "succeeded" and isinstance(nr.output, dict):
                cp.node_outputs[str(nr.node_instance_id)] = nr.output
        return cp

    def _is_pause_requested(self, execution_id: UUID) -> bool:
        """DB status가 PAUSED면 True. 조회 실패 시 보수적으로 False(중단 안 함)."""
        try:
            current = self._execution_repo.get(execution_id)
        except Exception:
            return False
        return getattr(current, "status", None) == ExecutionStatus.PAUSED

    @staticmethod
    def _step_node_ids(step) -> list[UUID]:
        if step.kind == "level":
            return [n.instance_id for n in step.level.nodes]
        return [n.instance_id for lvl in step.loop.levels for n in lvl.nodes]

    def _execute_loop(
        self,
        loop: LoopBody,
        context: ExecutionContext,
        configs: dict[UUID, Any],
        node_outputs: dict[str, dict[str, Any]],
        reachable: dict[UUID, bool],
        incoming: dict[UUID, list[Edge]],
        outgoing_handles: dict[UUID, list[str]],
        is_brancher: dict[UUID, bool],
        forced_live: set[Edge],
    ) -> tuple[list[NodeResult], bool]:
        """루프 바디를 가드 한도까지 반복 실행한다 (ADR-0023 L3).

        반환: (모든 iteration의 NodeResult, 실패 여부). 한 iteration 완료마다 back-edge
        liveness로 지속/탈출을 판정하고, 가드 도달 시 exit 엣지를 강제 live로 표시한다.
        """
        results: list[NodeResult] = []

        # 루프 진입 가능 여부 — 바디 진입 노드(levels[0])의 외부 incoming이 live여야 한다.
        # 안 탄 분기 위의 루프는 통째로 skip (L2 + L3 합성).
        entry = loop.levels[0].nodes if loop.levels else []
        if entry and not any(
            self._is_reachable(
                n, incoming, outgoing_handles, reachable, node_outputs, is_brancher, forced_live
            )
            for n in entry
        ):
            for body_level in loop.levels:
                for n in body_level.nodes:
                    reachable[n.instance_id] = False
                    skipped = self._skipped_result(n)
                    self._events.publish_node_complete(context.execution_id, skipped)
                    results.append(skipped)
            return results, False

        iteration = 0
        while True:
            for body_level in loop.levels:
                level_results = self._execute_level(
                    body_level, context, configs, node_outputs, reachable,
                    incoming, outgoing_handles, is_brancher, forced_live,
                    iteration=iteration, force_run=True,
                )
                results.extend(level_results)
                if self._orchestrator.has_failures(level_results):
                    return results, True

            if not self._loop_continues(loop, node_outputs, outgoing_handles, is_brancher):
                break  # 자연 탈출 — condition exit 핸들이 live → 하류는 L2가 처리
            iteration += 1
            if iteration >= loop.max_iterations:
                # 강제 탈출(best-effort): 미통과 결과라도 exit 엣지를 live로 하류 진행.
                forced_live.update(loop.exit_edges)
                break

        return results, False

    def _loop_continues(
        self,
        loop: LoopBody,
        node_outputs: dict[str, dict[str, Any]],
        outgoing_handles: dict[UUID, list[str]],
        is_brancher: dict[UUID, bool],
    ) -> bool:
        for e in loop.back_edges:
            src = e.from_instance_id
            src_out = node_outputs.get(str(src))
            if src_out is None:
                continue
            if self._branch.is_edge_live(
                is_brancher.get(src, False), src_out, outgoing_handles.get(src, []), e.from_handle
            ):
                return True
        return False

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
        forced_live: set[Edge],
        iteration: int = 0,
        force_run: bool = False,
    ) -> list[NodeResult]:
        # 도달 가능 노드만 실행, 나머지는 skip (ADR-0023 L2). 루프 바디는 force_run.
        results: list[NodeResult] = []
        to_run = []
        for node in level.nodes:
            if force_run or self._is_reachable(
                node, incoming, outgoing_handles, reachable, node_outputs, is_brancher, forced_live
            ):
                reachable[node.instance_id] = True
                to_run.append(node)
            else:
                reachable[node.instance_id] = False
                skipped = self._skipped_result(node, iteration)
                self._events.publish_node_complete(context.execution_id, skipped)
                results.append(skipped)

        if len(to_run) == 1:
            results.append(self._dispatch_single(to_run[0], context, configs, node_outputs, iteration))
        elif to_run:
            with ThreadPoolExecutor(max_workers=len(to_run)) as pool:
                futures = {
                    pool.submit(
                        self._dispatch_single, node, context, configs, node_outputs, iteration
                    ): node
                    for node in to_run
                }
                for future in as_completed(futures):
                    results.append(future.result())

        # 레벨 완료 후 성공 출력을 누적 — 하류/다음 iteration의 ${ref} 소스 (L1, latest-wins).
        for r in results:
            if r.status == "succeeded" and isinstance(r.output, dict):
                node_outputs[str(r.node_instance_id)] = r.output

        return results

    def _is_reachable(
        self,
        node,
        incoming: dict[UUID, list[Edge]],
        outgoing_handles: dict[UUID, list[str]],
        reachable: dict[UUID, bool],
        node_outputs: dict[str, dict[str, Any]],
        is_brancher: dict[UUID, bool],
        forced_live: set[Edge],
    ) -> bool:
        inc = incoming.get(node.instance_id, [])
        if not inc:
            return True  # 루트 노드는 항상 실행
        for e in inc:
            if e in forced_live:
                return True  # 가드 초과 루프의 강제 exit (L3)
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
    def _skipped_result(node, iteration: int = 0) -> NodeResult:
        now = datetime.now(UTC)
        return NodeResult(
            node_instance_id=node.instance_id,
            status="skipped",
            output={},
            started_at=now,
            completed_at=now,
            iteration=iteration,
        )

    def _dispatch_single(
        self, node, context: ExecutionContext, configs: dict[UUID, Any],
        node_outputs: dict[str, dict[str, Any]], iteration: int = 0,
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
            iteration=iteration,
        )
        self._events.publish_node_complete(context.execution_id, node_result)
        return node_result
