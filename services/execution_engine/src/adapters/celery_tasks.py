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

    result = use_case.execute(UUID(workflow_id), context)
    return result.model_dump(mode="json")


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
