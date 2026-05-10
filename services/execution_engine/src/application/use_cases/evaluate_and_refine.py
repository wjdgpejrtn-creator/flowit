from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID, uuid4

from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import ExecutionError
from common_schemas.handoff import EvaluationResult

from ...domain.entities.execution_context import ExecutionContext
from ...domain.entities.execution_result import ExecutionResult
from ...domain.ports.execution_repository_port import ExecutionRepositoryPort
from ...domain.ports.workflow_repository_port import WorkflowRepositoryPort
from .execute_workflow import ExecuteWorkflowUseCase

logger = logging.getLogger(__name__)

MAX_REFINE_ATTEMPTS = 3
PASS_THRESHOLD = 8.0


class EvaluateAndRefineUseCase:

    def __init__(
        self,
        execution_repo: ExecutionRepositoryPort,
        workflow_repo: WorkflowRepositoryPort,
        execute_workflow: ExecuteWorkflowUseCase,
    ) -> None:
        self._execution_repo = execution_repo
        self._workflow_repo = workflow_repo
        self._execute_workflow = execute_workflow

    def execute(
        self,
        execution_id: UUID,
        evaluation: EvaluationResult,
    ) -> Optional[ExecutionResult]:
        if evaluation.pass_flag or evaluation.score >= PASS_THRESHOLD:
            logger.info(
                "QA passed (score=%.1f) for execution=%s",
                evaluation.score,
                execution_id,
            )
            return None

        original = self._execution_repo.get(execution_id)
        attempt = original.node_results.__len__()  # rough proxy for attempt tracking

        if attempt >= MAX_REFINE_ATTEMPTS:
            raise ExecutionError(
                f"Maximum refine attempts ({MAX_REFINE_ATTEMPTS}) exceeded",
                code="E_MAX_REFINE_EXCEEDED",
            )

        logger.info(
            "QA failed (score=%.1f, reason=%s). Re-executing workflow=%s",
            evaluation.score,
            evaluation.reason,
            original.workflow_id,
        )

        context = ExecutionContext(
            execution_id=uuid4(),
            workflow_id=original.workflow_id,
            user_id=UUID("00000000-0000-0000-0000-000000000000"),
            trigger_type="handoff",
            parameters={
                "refine_feedback": evaluation.feedback,
                "previous_execution_id": str(execution_id),
                "qa_score": evaluation.score,
            },
        )

        return self._execute_workflow.execute(original.workflow_id, context)
