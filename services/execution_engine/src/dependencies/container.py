from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import cached_property
from typing import Any

from ..adapters.catalog_node_executor import CatalogNodeExecutor
from ..adapters.celery_adapter import CeleryAdapter
from ..adapters.sse_event_publisher import SSEEventPublisher
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
        event_publisher: Any,
        task_queue: Any | None = None,
    ) -> None:
        self._workflow_repo = workflow_repo
        self._execution_repo = execution_repo
        self._node_executor = node_executor
        self._event_publisher = event_publisher
        self._task_queue = task_queue

        self._scheduler = TopologicalScheduler()
        self._orchestrator = ExecutionOrchestrator(self._scheduler)
        self._retry_manager = RetryManager()

    @cached_property
    def dispatch_node_use_case(self) -> DispatchNodeUseCase:
        return DispatchNodeUseCase(
            node_executor=self._node_executor,
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


def _build_credential_service_factory():
    """credential 해결용 async 리소스 팩토리 (ADR-0018 Phase 2b).

    `CredentialInjectionService` + storage repository는 전부 `AsyncSession`(asyncpg)
    기반인데, sync Celery worker는 `_build_db_engine()`의 sync engine만 보유한다.
    `CatalogNodeExecutor`가 노드 실행 1회당 `asyncio.run()`으로 새 이벤트 루프를
    생성하므로, 워커 수명 동안 단일 async engine/connector를 보유하면 cross-loop로
    깨진다(asyncpg connection·Cloud SQL connector 모두 생성 루프에 바인딩).

    → credential 주입이 필요한 노드 실행 1회당 connector + async engine을 fresh
    생성하고 종료 시 dispose한다(`NullPool` — 단일 세션 1회용). credential_id가
    없는 노드는 본 팩토리를 호출하지 않으므로 비용을 지불하지 않는다.
    """
    from auth.adapters.cipher.aes_gcm import AESGCMCipher

    instance = os.getenv("CLOUD_SQL_INSTANCE")
    iam_user = os.getenv("DB_IAM_USER")
    db_name = os.getenv("DB_NAME")
    if not (instance and iam_user and db_name):
        raise RuntimeError(
            "credential resolver는 CLOUD_SQL_INSTANCE / DB_IAM_USER / DB_NAME "
            "환경변수를 요구한다 (Cloud SQL IAM auth). secret_env_vars 바인딩 확인."
        )

    # AESGCMCipher는 ENCRYPTION_KEY 환경변수를 생성 시 읽는다 — worker secret_env_vars
    # 에 encryption-key 바인딩 필요(infra/terraform/.../staging/main.tf).
    cipher = AESGCMCipher()

    # #452 ② OAuth access token refresh client (service-agnostic). GOOGLE_CLIENT_ID/SECRET가
    # worker secret_env_vars에 바인딩됐을 때만 google client를 배선한다 — 미바인딩이면 빈 dict로
    # degrade(만료 토큰은 기존처럼 401, deploy-safe). _build_skill_document_store 선례 미러.
    oauth_clients: dict[str, Any] = {}
    if os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"):
        from auth.adapters.oauth.google_oauth_client import GoogleOAuthClient

        oauth_clients["google"] = GoogleOAuthClient()

    @asynccontextmanager
    async def factory() -> AsyncIterator[Any]:
        from auth.domain.services.credential_injection_service import (
            CredentialInjectionService,
        )
        from google.cloud.sql.connector import IPTypes, create_async_connector
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool
        from storage.repositories.pg_credential_repository import PgCredentialRepository
        from storage.repositories.pg_node_definition_repository import (
            PgNodeDefinitionRepository,
        )
        from storage.repositories.pg_oauth_repository import PgOAuthRepository

        # create_async_connector()는 현재 실행 중인 이벤트 루프를 캡처한다 —
        # asyncio.run()이 만든 루프에 바인딩되어 본 with 블록 내에서만 유효.
        connector = await create_async_connector()

        async def getconn():
            return await connector.connect_async(
                instance,
                "asyncpg",
                user=iam_user,
                db=db_name,
                enable_iam_auth=True,
                ip_type=IPTypes.PUBLIC,
            )

        engine = create_async_engine(
            "postgresql+asyncpg://",
            async_creator=getconn,
            poolclass=NullPool,
        )
        try:
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                yield CredentialInjectionService(
                    cipher=cipher,
                    oauth_repo=PgOAuthRepository(session),
                    node_def_repo=PgNodeDefinitionRepository(session),
                    credential_repo=PgCredentialRepository(session),
                    oauth_clients=oauth_clients,
                )
                # #452 ② inject()가 만료 토큰을 refresh하면 update_tokens 쓰기가 발생한다.
                # 정상 종료 시 commit해 갱신 토큰을 영속화(다음 주입 재갱신 비용 절감 + expires_at
                # backfill). 소비자(inject)가 예외를 던지면 yield에서 전파돼 이 commit은 건너뛰고
                # AsyncSession.__aexit__이 rollback한다. read-only 경로는 쓰기 없어 no-op commit.
                await session.commit()
        finally:
            await engine.dispose()
            await connector.close_async()

    return factory


def _build_skill_document_store() -> Any:
    """바인딩된 스킬 지침서(SkillDocument) 로더. `SKILLS_MARKETPLACE_BUCKET` 미설정 시 None.

    None이면 CatalogNodeExecutor가 skill 주입을 무주입 degrade(기존 동작)하므로 env 추가
    전까지 deploy-safe. GCS는 asyncpg 이벤트 루프 바인딩과 무관하므로 단일 인스턴스 주입으로
    충분하다 (credential service factory의 fresh-engine 패턴 불요). api_server
    dependencies/storage.py 선례 미러.
    """
    bucket = os.getenv("SKILLS_MARKETPLACE_BUCKET")
    if not bucket:
        return None
    from storage.adapters.gcs_adapter import GCSAdapter
    from storage.adapters.gcs_skill_document_store import GcsSkillDocumentStore

    return GcsSkillDocumentStore(object_storage=GCSAdapter(bucket_name=bucket))


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
    node_executor = CatalogNodeExecutor(
        get_all_node_classes(),
        credential_service_factory=_build_credential_service_factory(),
        skill_document_store=_build_skill_document_store(),
    )

    from .._celery_app import celery_app

    task_queue = CeleryAdapter(celery_app)

    _container = Container(
        workflow_repo=workflow_repo,
        execution_repo=execution_repo,
        node_executor=node_executor,
        event_publisher=event_publisher,
        task_queue=task_queue,
    )
    return _container
