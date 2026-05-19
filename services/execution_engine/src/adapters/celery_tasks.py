from __future__ import annotations

from uuid import UUID

from celery import shared_task

from ..domain.entities.execution_context import ExecutionContext


@shared_task(
    name="execution_engine.execute_workflow",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def execute_workflow_task(self, workflow_id: str, context_data: dict) -> dict:
    from ..dependencies.container import create_container

    container = create_container()
    use_case = container.execute_workflow_use_case

    context = ExecutionContext(
        execution_id=UUID(context_data["execution_id"]),
        workflow_id=UUID(context_data["workflow_id"]),
        user_id=UUID(context_data["user_id"]),
        trigger_type=context_data["trigger_type"],
        parameters=context_data.get("parameters", {}),
    )

    # cancel_execution_task가 revoke 시 사용할 task_id를 ExecutionRepository에 영속화.
    # 워크플로우 실행 시작 직전에 task_id를 저장해 cancel 가능성 확보.
    try:
        existing = container._execution_repo.get(context.execution_id)
        existing.celery_task_id = self.request.id
        container._execution_repo.save(existing)
    except Exception:
        # 첫 실행 시 row가 없을 수 있음 — execute_workflow가 알아서 INSERT.
        # 그 경로에서는 celery_task_id 누락. 보강: ExecuteWorkflowUseCase가
        # 첫 save 시 context에서 task_id 받아 저장하도록 후속 PR.
        pass

    result = use_case.execute(UUID(workflow_id), context)
    return result.model_dump(mode="json")


@shared_task(
    name="execution_engine.cancel_execution",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def cancel_execution_task(self, execution_id: str) -> dict:
    from ..dependencies.container import create_container

    container = create_container()
    use_case = container.pause_resume_use_case
    use_case.execute(UUID(execution_id), action="cancel")
    return {"execution_id": execution_id, "action": "cancel", "status": "cancelled"}


@shared_task(
    name="execution_engine.resume_execution",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def resume_execution_task(self, execution_id: str) -> dict:
    from ..dependencies.container import create_container

    container = create_container()
    use_case = container.pause_resume_use_case
    use_case.execute(UUID(execution_id), action="resume")
    return {"execution_id": execution_id, "action": "resume", "status": "running"}


@shared_task(
    name="execution_engine.execute_node",
    bind=True,
    max_retries=3,
    acks_late=True,
)
def execute_node_task(
    self,
    node_data: dict,
    config_data: dict,
    inputs: dict,
    user_id: str,
    execution_id: str,
) -> dict:
    from common_schemas.workflow import NodeConfig, NodeInstance

    from ..dependencies.container import create_container

    container = create_container()
    dispatch_node = container.dispatch_node_use_case

    node = NodeInstance.model_validate(node_data)
    config = NodeConfig.model_validate(config_data)

    node_result = dispatch_node.execute(
        node=node,
        config=config,
        inputs=inputs,
        user_id=UUID(user_id),
        execution_id=UUID(execution_id),
    )
    return node_result.model_dump(mode="json")


@shared_task(
    name="execution_engine.handle_handoff",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def handle_handoff_task(self, payload_data: dict) -> dict:
    from common_schemas.handoff import HandoffPayload

    from ..dependencies.container import create_container

    container = create_container()
    use_case = container.handle_handoff_use_case

    payload = HandoffPayload.model_validate(payload_data)
    result = use_case.execute(payload)
    return result.model_dump(mode="json")


@shared_task(name="execution_engine.level_callback", bind=True)
def level_callback_task(self, results: list[dict], execution_id: str) -> dict:
    return {
        "execution_id": execution_id,
        "node_results": results,
        "status": "level_complete",
    }
