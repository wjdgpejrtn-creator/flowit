"""Celery broker task name constants — single source of truth.

api_server(`send_task`) + execution_engine(`@shared_task(name=...)`) 양쪽이 같은 문자열을
참조하도록 SSOT 모듈. 이전엔 각자 매직 문자열로 정의 → drift 위험 (PR #75 + PR #89 검토).

사용:

    from common_schemas.broker_tasks import TASK_EXECUTE_WORKFLOW
    celery.send_task(TASK_EXECUTE_WORKFLOW, args=[...])

    @shared_task(name=TASK_EXECUTE_WORKFLOW)
    def execute_workflow_task(...): ...

Naming convention: ``execution_engine.<verb>`` — Celery queue routing 패턴과 정합.
"""
from __future__ import annotations

# REQ-007 execution_engine task names
TASK_EXECUTE_WORKFLOW: str = "execution_engine.execute_workflow"
TASK_CANCEL_EXECUTION: str = "execution_engine.cancel_execution"
TASK_RESUME_EXECUTION: str = "execution_engine.resume_execution"
TASK_EXECUTE_NODE: str = "execution_engine.execute_node"
TASK_HANDLE_HANDOFF: str = "execution_engine.handle_handoff"
TASK_LEVEL_CALLBACK: str = "execution_engine.level_callback"

# Default Celery queue
QUEUE_DEFAULT: str = "default"
