from __future__ import annotations

import os
from functools import cached_property
from typing import Any

from ..adapters.catalog_node_executor import CatalogNodeExecutor
from ..adapters.celery_adapter import CeleryAdapter
from ..adapters.sse_event_publisher import SSEEventPublisher
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


def _build_redis_client():
    """Redis 클라이언트 — rediss://(TLS) 시 Memorystore SERVER_AUTHENTICATION cert가
    컨테이너 trust store에 없어 cert verify skip. TLS encryption은 유지."""
    import redis

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return redis.Redis()
    kwargs: dict = {}
    if redis_url.startswith("rediss://"):
        kwargs["ssl_cert_reqs"] = None
    return redis.Redis.from_url(redis_url, **kwargs)


def _build_db_engine():
    """Cloud SQL IAM 인증 sync engine — [[sub_agent_cloud_sql_iam]] 표준.

    pg8000(순수 Python driver) + cloud-sql-python-connector. 비밀번호 DSN 금지.
    Celery worker는 sync이므로 async connector 대신 sync `Connector`를 사용한다.
    """
    from google.cloud.sql.connector import Connector, IPTypes
    from sqlalchemy import create_engine

    instance = os.getenv("CLOUD_SQL_INSTANCE")
    iam_user = os.getenv("DB_IAM_USER")
    db_name = os.getenv("DB_NAME")
    if not (instance and iam_user and db_name):
        raise RuntimeError(
            "execution_engine DB engine은 CLOUD_SQL_INSTANCE / DB_IAM_USER / DB_NAME "
            "환경변수를 요구한다 (Cloud SQL IAM auth). secret_env_vars 바인딩 확인."
        )

    connector = Connector()

    def getconn():
        return connector.connect(
            instance,
            "pg8000",
            user=iam_user,
            db=db_name,
            enable_iam_auth=True,
            ip_type=IPTypes.PUBLIC,
        )

    return create_engine("postgresql+pg8000://", creator=getconn, pool_pre_ping=True)


def create_container() -> Container:
    global _container
    if _container is not None:
        return _container

    from nodes_graph.application.catalog_registry import get_all_node_classes
    from sqlalchemy.orm import sessionmaker

    from ..adapters.postgres_execution_repo import PostgresExecutionRepository
    from ..adapters.postgres_workflow_repo import PostgresWorkflowRepository

    redis_client = _build_redis_client()
    engine = _build_db_engine()
    session_factory = sessionmaker(bind=engine)

    workflow_repo = PostgresWorkflowRepository(session_factory)
    execution_repo = PostgresExecutionRepository(session_factory)
    event_publisher = SSEEventPublisher(redis_client)
    credential_provider = VaultCredentialProvider(credential_store=_noop_credential_store)
    node_executor = CatalogNodeExecutor(get_all_node_classes())

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
