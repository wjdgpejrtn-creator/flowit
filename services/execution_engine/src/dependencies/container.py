from __future__ import annotations

import os
from functools import cached_property
from typing import Any

from ..adapters.celery_adapter import CeleryAdapter
from ..adapters.sse_event_publisher import SSEEventPublisher
from ..adapters.toolset_executor import ToolsetExecutor
from ..adapters.vault_credential_provider import VaultCredentialProvider
from ..application.use_cases.dispatch_node import DispatchNodeUseCase
from ..application.use_cases.evaluate_and_refine import EvaluateAndRefineUseCase
from ..application.use_cases.execute_workflow import ExecuteWorkflowUseCase
from ..application.use_cases.handle_handoff import HandleHandoffUseCase
from ..application.use_cases.pause_resume import PauseResumeUseCase
from ..domain.services.execution_orchestrator import ExecutionOrchestrator
from ..domain.services.retry_manager import RetryManager
from ..domain.services.topological_scheduler import TopologicalScheduler


class Container:

    def __init__(
        self,
        workflow_repo: Any,
        execution_repo: Any,
        node_executor: Any,
        credential_provider: Any,
        event_publisher: Any,
        task_queue: Any | None = None,
    ) -> None:
        self._workflow_repo = workflow_repo
        self._execution_repo = execution_repo
        self._node_executor = node_executor
        self._credential_provider = credential_provider
        self._event_publisher = event_publisher
        self._task_queue = task_queue

        self._scheduler = TopologicalScheduler()
        self._orchestrator = ExecutionOrchestrator(self._scheduler)
        self._retry_manager = RetryManager()

    @cached_property
    def dispatch_node_use_case(self) -> DispatchNodeUseCase:
        return DispatchNodeUseCase(
            node_executor=self._node_executor,
            credential_provider=self._credential_provider,
            event_publisher=self._event_publisher,
            retry_manager=self._retry_manager,
        )

    @cached_property
    def execute_workflow_use_case(self) -> ExecuteWorkflowUseCase:
        return ExecuteWorkflowUseCase(
            workflow_repo=self._workflow_repo,
            execution_repo=self._execution_repo,
            orchestrator=self._orchestrator,
            dispatch_node=self.dispatch_node_use_case,
            event_publisher=self._event_publisher,
        )

    @cached_property
    def handle_handoff_use_case(self) -> HandleHandoffUseCase:
        return HandleHandoffUseCase(
            workflow_repo=self._workflow_repo,
            execute_workflow=self.execute_workflow_use_case,
        )

    @cached_property
    def pause_resume_use_case(self) -> PauseResumeUseCase:
        return PauseResumeUseCase(
            execution_repo=self._execution_repo,
            event_publisher=self._event_publisher,
            orchestrator=self._orchestrator,
            task_queue=self._task_queue,
        )

    @cached_property
    def evaluate_and_refine_use_case(self) -> EvaluateAndRefineUseCase:
        return EvaluateAndRefineUseCase(
            execution_repo=self._execution_repo,
            workflow_repo=self._workflow_repo,
            execute_workflow=self.execute_workflow_use_case,
        )


_container: Container | None = None


def create_container() -> Container:
    global _container
    if _container is not None:
        return _container

    import redis

    from ..adapters.postgres_execution_repo import PostgresExecutionRepository
    from ..adapters.postgres_workflow_repo import PostgresWorkflowRepository

    redis_url = os.getenv("REDIS_URL")
    redis_client = redis.Redis.from_url(redis_url) if redis_url else redis.Redis()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_host = os.getenv("DB_HOST")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")
    database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    engine = create_engine(database_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine)

    workflow_repo = PostgresWorkflowRepository(session_factory)
    execution_repo = PostgresExecutionRepository(session_factory)
    event_publisher = SSEEventPublisher(redis_client)
    credential_provider = VaultCredentialProvider(credential_store=_noop_credential_store)
    node_executor = ToolsetExecutor(execute_tool=_noop_tool_executor)

    from .._celery_app import celery_app

    task_queue = CeleryAdapter(celery_app)

    _container = Container(
        workflow_repo=workflow_repo,
        execution_repo=execution_repo,
        node_executor=node_executor,
        credential_provider=credential_provider,
        event_publisher=event_publisher,
        task_queue=task_queue,
    )
    return _container


class _NoopCredentialStore:
    def decrypt(self, credential_id, user_id):
        raise NotImplementedError("CredentialStore not wired — provide auth module adapter")


_noop_credential_store = _NoopCredentialStore()


def _noop_tool_executor(tool_name, input_data, credential_id=None, credentials=None, user_id=None):
    raise NotImplementedError("ToolsetExecutor not wired — provide toolset module adapter")
