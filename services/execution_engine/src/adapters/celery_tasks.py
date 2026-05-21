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

    # task_queue_id는 ExecutionContext를 통해 use case에 전달 → 첫 INSERT와 같은
    # transaction에 영속화. Container 내부 repo 직접 접근 / 별도 save 호출 없음.
    context = ExecutionContext(
        execution_id=UUID(context_data["execution_id"]),
        workflow_id=UUID(context_data["workflow_id"]),
        user_id=UUID(context_data["user_id"]),
        trigger_type=context_data["trigger_type"],
        parameters=context_data.get("parameters", {}),
        task_queue_id=self.request.id,
    )

    result = use_case.execute(UUID(workflow_id), context)
    return result.model_dump(mode="json")


@shared_task(
    name="execution_engine.cancel_execution",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def cancel_execution_task(self, execution_id: str) -> dict:
    from common_schemas.exceptions import DomainError

    from ..dependencies.container import create_container

    container = create_container()
    use_case = container.pause_resume_use_case
    try:
        use_case.execute(UUID(execution_id), action="cancel")
    except DomainError as exc:
        # 도메인 계층 오류는 사용자 입력 범주 → graceful skip. 종료된 execution을
        # cancel(ExecutionError, invalid transition)이든 존재하지 않는 execution
        # (NotFoundError)이든 입력 오류이지 시스템 장애가 아니다 — task를 ERROR로
        # 올리면 로그 노이즈 + task 실패율이 왜곡된다. broker 장애 등 비-DomainError
        # 예외는 그대로 전파해 task 실패로 노출한다.
        return {
            "execution_id": execution_id,
            "action": "cancel",
            "status": "skipped",
            "reason": str(exc),
        }
    return {"execution_id": execution_id, "action": "cancel", "status": "cancelled"}


@shared_task(
    name="execution_engine.resume_execution",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def resume_execution_task(self, execution_id: str) -> dict:
    from common_schemas.exceptions import DomainError

    from ..dependencies.container import create_container

    container = create_container()
    use_case = container.pause_resume_use_case
    try:
        use_case.execute(UUID(execution_id), action="resume")
    except DomainError as exc:
        # 도메인 계층 오류(resume 불가 상태 ExecutionError / 존재하지 않는 execution
        # NotFoundError 등)는 사용자 입력 범주 → graceful skip. 비-DomainError 예외는
        # 그대로 전파한다. (cancel_execution_task 참고)
        return {
            "execution_id": execution_id,
            "action": "resume",
            "status": "skipped",
            "reason": str(exc),
        }
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
