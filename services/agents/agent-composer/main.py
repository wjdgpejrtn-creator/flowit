"""agent-composer — Workflow Composer Modal app (REQ-004 §3.2).

LangGraphOrchestrator(13노드)를 Modal ASGI app으로 노출.
Orchestrator로부터 AgentProtocolRequest를 받아 SSE 스트림으로 응답.

Deploy:
    PYTHONUTF8=1 modal deploy services/agents/agent-composer/main.py

Health:
    curl https://dhwang0803--agent-composer-agentcomposer-fastapi.modal.run/v1/health
"""
from __future__ import annotations

import modal

app_secret = modal.Secret.from_name("agent-composer-secret")
gcp_secret = modal.Secret.from_name("cloudsql-iam-sa")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi>=0.115",
        "httpx>=0.27",
        "pydantic>=2.13",
        "sqlalchemy[asyncio]>=2.0",
        "asyncpg>=0.30",
        "pgvector>=0.3",
        "cloud-sql-python-connector[asyncpg]>=1.12",
        "langgraph>=0.2",
        "modal>=0.73",
        "protobuf>=4.25",
        "jsonschema>=4.0",
    )
    .env({"PYTHONPATH": "/app/modules:/app/common_schemas_src"})
    .add_local_dir("modules", remote_path="/app/modules")
    .add_local_dir("packages/common_schemas/python", remote_path="/app/common_schemas_src")
)

app = modal.App("agent-composer")


@app.cls(
    image=image,
    secrets=[app_secret, gcp_secret],
    timeout=600,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=8)
class AgentComposer:
    """Workflow Composer — LangGraphOrchestrator(13노드) composition root."""

    @modal.enter()
    def boot(self) -> None:
        import os
        import tempfile
        from pathlib import Path
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        # GCP SA JSON → 임시 파일 → ADC 환경변수
        sa_payload = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
        sa_path = Path(tempfile.gettempdir()) / "gcp-sa.json"
        sa_path.write_text(sa_payload, encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa_path)

        # Connector를 getconn() 안에서 lazy 초기화 + 명시적 loop 바인딩
        # storage/orm/session_factory.py 동일 패턴 — ConnectorLoopError 해결
        self._connector = None

        async def getconn():
            import asyncio
            from google.cloud.sql.connector import Connector, IPTypes
            if self._connector is None:
                self._connector = Connector(loop=asyncio.get_running_loop())
            return await self._connector.connect_async(
                os.environ["CLOUD_SQL_INSTANCE"],
                "asyncpg",
                user=os.environ["DB_IAM_USER"],
                db=os.environ["DB_NAME"],
                enable_iam_auth=True,
                ip_type=IPTypes.PUBLIC,
            )

        self._engine = create_async_engine(
            "postgresql+asyncpg://",
            async_creator=getconn,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        # 어댑터 + 서비스 wiring
        from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter
        from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
        from ai_agent.adapters.node_registry_adapter import NodeRegistryAdapter
        from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
        from ai_agent.domain.services.intent_analyzer_service import IntentAnalyzerService
        from ai_agent.domain.services.drafter_service import DrafterService
        from ai_agent.domain.services.qa_evaluator_service import QAEvaluatorService
        from ai_agent.domain.services.slot_filling_service import SlotFillingService
        from nodes_graph.domain.services.graph_validator import GraphValidator
        from storage.repositories.pg_node_definition_repository import PgNodeDefinitionRepository
        from storage.repositories.pg_workflow_repository import PgWorkflowRepository

        llm = ModalLLMAdapter()
        embedder = ModalEmbeddingAdapter()

        node_repo = PgNodeDefinitionRepository(self._session_factory)
        workflow_repo = PgWorkflowRepository(self._session_factory)
        node_registry = NodeRegistryAdapter(node_repo, embedder)
        graph_validator = GraphValidator(node_repo)

        self._graph = LangGraphOrchestrator(
            intent_analyzer=IntentAnalyzerService(llm),
            drafter=DrafterService(llm),
            qa_evaluator=QAEvaluatorService(llm),
            slot_filler=SlotFillingService(),
            node_registry=node_registry,
            workflow_repo=workflow_repo,
            graph_validator=graph_validator,
        )

    @modal.exit()
    def shutdown(self) -> None:
        import asyncio
        if getattr(self, "_engine", None):
            asyncio.run(self._engine.dispose())
        if getattr(self, "_connector", None):
            asyncio.run(self._connector.close_async())

    @modal.asgi_app()
    def fastapi(self):
        import json
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import StreamingResponse
        from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse

        api = FastAPI(title="agent-composer", version="1.0")

        @api.get("/v1/health")
        async def health() -> dict[str, object]:
            import logging
            from sqlalchemy import text
            logger = logging.getLogger(__name__)
            try:
                async with self._engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            except Exception as exc:
                logger.warning("db unreachable: %s", repr(exc))
                raise HTTPException(
                    status_code=503,
                    detail={"db": "unreachable"},
                )
            return {"status": "ok", "db": "iam-connected"}

        @api.post("/v1/agent/route")
        async def route(req: AgentProtocolRequest):
            async def generate():
                try:
                    async for frame in await self._graph.stream(
                        user_id=req.user_id,
                        session_id=req.session_id,
                        message=req.payload.get("message", ""),
                        personal_memory=list(req.personal_memory),
                    ):
                        resp = AgentProtocolResponse(
                            frames=[frame],
                            state_delta={},
                            next_action="continue",
                        )
                        yield f"data: {resp.model_dump_json()}\n\n"
                except Exception as exc:
                    err = AgentProtocolResponse(
                        frames=[],
                        state_delta={"error": str(exc)},
                        next_action="error",
                    )
                    yield f"data: {err.model_dump_json()}\n\n"
                    done = AgentProtocolResponse(
                        frames=[],
                        state_delta={},
                        next_action="complete",
                    )
                    yield f"data: {done.model_dump_json()}\n\n"
                    return
                done = AgentProtocolResponse(
                    frames=[],
                    state_delta={},
                    next_action="complete",
                )
                yield f"data: {done.model_dump_json()}\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")

        return api
