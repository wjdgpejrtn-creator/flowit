from __future__ import annotations

from uuid import UUID, uuid4

from common_schemas.exceptions import ValidationError
from common_schemas.handoff import HandoffPayload

from ...domain.entities.execution_context import ExecutionContext
from ...domain.entities.execution_result import ExecutionResult
from ...domain.ports.workflow_repository_port import WorkflowRepositoryPort
from .execute_workflow import ExecuteWorkflowUseCase


class HandleHandoffUseCase:

    def __init__(
        self,
        workflow_repo: WorkflowRepositoryPort,
        execute_workflow: ExecuteWorkflowUseCase,
    ) -> None:
        self._workflow_repo = workflow_repo
        self._execute_workflow = execute_workflow

    def execute(self, payload: HandoffPayload) -> ExecutionResult:
        workflow_id_str = payload.state_data.get("workflow_id")
        if not workflow_id_str:
            raise ValidationError(
                "HandoffPayload.state_data must contain 'workflow_id'",
                code="E_MISSING_WORKFLOW_ID",
            )

        workflow_id = UUID(workflow_id_str)

        user_id_str = payload.state_data.get("user_id")
        if not user_id_str:
            raise ValidationError(
                "HandoffPayload.state_data must contain 'user_id'",
                code="E_MISSING_USER_ID",
            )

        context = ExecutionContext(
            execution_id=uuid4(),
            workflow_id=workflow_id,
            user_id=UUID(user_id_str),
            trigger_type="handoff",
            parameters=payload.state_data.get("parameters", {}),
        )

        return self._execute_workflow.execute(workflow_id, context)
