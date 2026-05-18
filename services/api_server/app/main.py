from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.dependencies.auth import get_jwt_adapter, get_permission_resolver
from app.dependencies.clients import (
    dispose_orchestrator_http,
    dispose_redis,
    init_orchestrator_http,
    init_redis,
)
from app.dependencies.database import dispose_db_engine, init_db_engine
from app.middleware.auth import AuthMiddleware
from app.middleware.cors import install_cors
from app.middleware.error_handler import install_error_handlers
from app.middleware.request_id import RequestIdMiddleware
from app.routers import auth as auth_router
from app.routers import health
from app.routers import nodes as nodes_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    engine = await init_db_engine(settings)
    app.state.db_engine = engine
    app.state.db_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app.state.redis = await init_redis(settings)
    app.state.orchestrator_http = init_orchestrator_http(settings)

    logger.info("api_server lifespan: ready")
    try:
        yield
    finally:
        await dispose_orchestrator_http(app.state.orchestrator_http)
        await dispose_redis(app.state.redis)
        await dispose_db_engine(app.state.db_engine)
        logger.info("api_server lifespan: shutdown complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]

    app = FastAPI(
        title="Workflow Automation API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/v1/openapi.json",
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
    )

    install_error_handlers(app)

    app.include_router(health.router)
    app.include_router(auth_router.router)
    app.include_router(nodes_router.router)
    return app
