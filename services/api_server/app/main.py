from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.dependencies.auth import get_jwt_adapter, get_permission_resolver
from app.dependencies.celery_client import init_celery
from app.dependencies.clients import (
    dispose_orchestrator_http,
    dispose_redis,
    dispose_skills_builder_http,
    init_orchestrator_http,
    init_redis,
    init_skills_builder_http,
)
from app.dependencies.database import dispose_db_engine, init_db_engine
from app.middleware.auth import API_SERVER_PUBLIC_PATHS, AuthMiddleware
from app.middleware.cors import install_cors
from app.middleware.error_handler import install_error_handlers
from app.middleware.request_id import RequestIdMiddleware
from app.routers import auth as auth_router
from app.routers import documents as documents_router
from app.routers import exec_control as exec_control_router
from app.routers import health
from app.routers import nodes as nodes_router
from app.routers import skills as skills_router
from app.routers import workflows as workflows_router
from app.routers.agents import agents_router, ai_sessions_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    db_handle = await init_db_engine(settings)
    app.state.db_handle = db_handle
    app.state.db_session_factory = async_sessionmaker(db_handle.engine, expire_on_commit=False)

    app.state.redis = await init_redis(settings)
    app.state.orchestrator_http = init_orchestrator_http(settings)
    app.state.skills_builder_http = init_skills_builder_http(settings)
    app.state.celery = init_celery(settings)

    logger.info("api_server lifespan: ready")
    try:
        yield
    finally:
        await dispose_orchestrator_http(app.state.orchestrator_http)
        await dispose_skills_builder_http(app.state.skills_builder_http)
        await dispose_redis(app.state.redis)
        await dispose_db_engine(app.state.db_handle)
        logger.info("api_server lifespan: shutdown complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]

    # production에서는 OpenAPI/Swagger docs 비공개. staging/dev는 노출.
    docs_url = None if settings.is_production() else "/api/docs"
    openapi_url = None if settings.is_production() else "/api/v1/openapi.json"

    app = FastAPI(
        title="Workflow Automation API",
        version="0.1.0",
        docs_url=docs_url,
        openapi_url=openapi_url,
        lifespan=_lifespan,
    )
    app.state.settings = settings

    # Middleware (등록 역순으로 실행됨 — 위쪽이 outermost)
    install_cors(app, settings)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        AuthMiddleware,
        jwt_adapter=get_jwt_adapter(),
        permission_resolver=get_permission_resolver(),
        extra_public_paths=API_SERVER_PUBLIC_PATHS,
    )

    install_error_handlers(app)

    app.include_router(health.router)
    app.include_router(auth_router.router)
    app.include_router(agents_router)
    app.include_router(ai_sessions_router)
    app.include_router(nodes_router.router)
    app.include_router(workflows_router.router)
    app.include_router(exec_control_router.router)
    app.include_router(skills_router.router)
    app.include_router(documents_router.router)
    return app
