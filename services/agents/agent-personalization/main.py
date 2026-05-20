"""agent-personalization — Personalization sub-agent Modal app.

Actions (payload["action"]):
  load_memory    — LoadUserMemoryUseCase  (GCS → list[MemoryEntry])
  update_memory  — UpdateUserMemoryUseCase (LLM 패턴 추출 → GCS 저장)
  recall_skills  — RecallPersonalSkillsUseCase (BGE-M3 코사인 유사도 top-k)
  save_memory    — SaveMemoryUseCase (RDB AgentMemoryRepository)
  cleanup_memory — GCSMemoryStore 인메모리 캐시 정리 (세션 종료 시)

Deploy:
    PYTHONUTF8=1 modal deploy services/agents/agent-personalization/main.py

Health:
    curl https://dhwang0803--agent-personalization-personalizationagent-fastapi.modal.run/v1/health
"""
import os
from pathlib import Path

import modal

APP_NAME = "agent-personalization"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "fastapi>=0.115",
        "httpx>=0.27",
        "pydantic>=2.13",
        "sqlalchemy[asyncio]>=2.0",
        "asyncpg>=0.30",
        "pgvector>=0.3",
        "cloud-sql-python-connector[asyncpg]>=1.12",
        "google-cloud-storage>=2.0",
        "google-cloud-secret-manager>=2.20",
        "modal>=0.73",
        "protobuf>=4.25",
        "PyJWT>=2.8",
        "jsonschema>=4.0",
        "jmespath>=1.0",
    )
    .env({
        "PYTHONPATH": "/pkg/common_schemas:/pkg:/repo",
        "GOOGLE_CLOUD_PROJECT": "<GCP_PROJECT_ID>",
    })
    .add_local_dir("packages/common_schemas/python", remote_path="/pkg/common_schemas", copy=True)
    .add_local_dir("modules/auth", remote_path="/pkg/auth", copy=True)
    .add_local_dir("modules/nodes_graph", remote_path="/pkg/nodes_graph", copy=True)
    .add_local_dir("modules/storage", remote_path="/pkg/storage", copy=True)
    .add_local_dir("modules/ai_agent", remote_path="/pkg/ai_agent", copy=True)
    .add_local_dir("modules/toolset", remote_path="/pkg/toolset", copy=True)
    .add_local_dir("services/common", remote_path="/repo/services/common", copy=True)
)

gcp_secret = modal.Secret.from_name("cloudsql-iam-sa")

app = modal.App(APP_NAME)


@app.cls(
    image=image,
    secrets=[gcp_secret],
    timeout=600,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=8)
class PersonalizationAgent:

    @modal.enter()
    def boot(self) -> None:
        import tempfile
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from services.common.gcp_secrets import load_secrets_to_env

        # GCP SA JSON → 임시 파일 → ADC 환경변수
        sa_payload = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
        sa_path = Path(tempfile.gettempdir()) / "gcp-sa.json"
        sa_path.write_text(sa_payload, encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa_path)

        # GCP Secret Manager → 환경변수 주입
        load_secrets_to_env({
            "cloud-sql-instance":  "CLOUD_SQL_INSTANCE",
            "db-iam-user":         "DB_IAM_USER",
            "db-name":             "DB_NAME",
            "llm-base-url":        "LLM_BASE_URL",
            "embedding-base-url":  "EMBEDDING_BASE_URL",
            "gcs-personal-bucket": "GCS_PERSONAL_BUCKET",
        })

        # Connector를 getconn() 안에서 lazy 초기화 — ConnectorLoopError 방지
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

        # 어댑터 wiring
        from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
        from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter
        from ai_agent.adapters.memory.gcs_memory_store import GCSMemoryStore
        from toolset.adapters.tool_registry_adapter import ToolRegistryAdapter
        from toolset.bootstrap import register_default_tools

        self._llm = ModalLLMAdapter()
        self._embedder = ModalEmbeddingAdapter()
        self._memory_store = GCSMemoryStore()

        # tool registry — 14종 기본 tool 등록
        self._tool_registry = ToolRegistryAdapter()
        register_default_tools(self._tool_registry)
        # TODO: self._tool_dispatcher = ToolsetDispatcher(ExecuteToolUseCase(self._tool_registry))
        #       신정혜 항목 4(ToolsetDispatcher) 완료 후 주입

    @modal.exit()
    def shutdown(self) -> None:
        import asyncio

        if getattr(self, "_engine", None):
            asyncio.run(self._engine.dispose())
        if getattr(self, "_connector", None):
            asyncio.run(self._connector.close_async())

    @modal.asgi_app()
    def fastapi(self) -> "FastAPI":
        from fastapi import Body, FastAPI, HTTPException
        from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse

        api = FastAPI(title=APP_NAME, debug=os.getenv("DEBUG") == "1")

        @api.post("/v1/agent/route", response_model=AgentProtocolResponse)
        async def route(req: AgentProtocolRequest = Body(...)) -> AgentProtocolResponse:
            action = req.payload.get("action")

            if action == "load_memory":
                from ai_agent.application.agents.personalization import LoadUserMemoryUseCase

                entries = await LoadUserMemoryUseCase(self._memory_store).execute(req.user_id)
                return AgentProtocolResponse(
                    frames=[],
                    state_delta={"personal_memory": [e.model_dump() for e in entries]},
                    next_action="complete",
                )

            if action == "update_memory":
                from common_schemas import WorkflowSchema
                from ai_agent.application.agents.personalization import UpdateUserMemoryUseCase

                workflow_data = req.payload.get("workflow")
                workflow = WorkflowSchema.model_validate(workflow_data) if workflow_data else None
                await UpdateUserMemoryUseCase(
                    self._memory_store, self._llm
                ).execute(
                    req.user_id,
                    req.payload.get("turn_count", 0),
                    req.payload.get("session_summary"),
                    workflow,
                )
                return AgentProtocolResponse(frames=[], state_delta={}, next_action="complete")

            if action == "recall_skills":
                from ai_agent.application.agents.personalization import RecallPersonalSkillsUseCase

                skills = await RecallPersonalSkillsUseCase(
                    self._memory_store, self._embedder,
                    top_k=req.payload.get("limit", 5),
                ).execute(
                    req.user_id,
                    query=req.payload["query"],
                )
                return AgentProtocolResponse(
                    frames=[],
                    state_delta={"recalled_skills": [s.model_dump() for s in skills]},
                    next_action="complete",
                )

            if action == "save_memory":
                from common_schemas import MemoryEntry
                from ai_agent.application.agents.personalization import SaveMemoryUseCase
                from storage.repositories.pg_agent_memory_repository import PgAgentMemoryRepository

                entries = [MemoryEntry.model_validate(e) for e in req.payload.get("entries", [])]
                async with self._session_factory() as session:
                    await SaveMemoryUseCase(PgAgentMemoryRepository(session)).execute(
                        req.session_id, entries
                    )
                return AgentProtocolResponse(frames=[], state_delta={}, next_action="complete")

            if action == "cleanup_memory":
                await self._memory_store.cleanup(req.user_id)
                return AgentProtocolResponse(frames=[], state_delta={}, next_action="complete")

            raise HTTPException(status_code=400, detail=f"Unknown action: {action!r}")

        @api.get("/v1/health")
        async def health() -> dict[str, object]:
            import asyncio
            from sqlalchemy import text

            try:
                async with self._engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                db_ok, db_err = True, None
            except Exception as exc:
                db_ok, db_err = False, repr(exc)

            try:
                from google.cloud import storage as gcs
                bucket_name = os.environ.get("GCS_PERSONAL_BUCKET", "")
                client = gcs.Client()
                bucket = client.bucket(bucket_name)
                await asyncio.to_thread(bucket.reload)
                gcs_ok, gcs_err = True, None
            except Exception as exc:
                gcs_ok, gcs_err = False, repr(exc)

            errors: dict[str, object] = {}
            if not db_ok:
                errors["db"] = {"ok": False, "error": db_err}
            if not gcs_ok:
                errors["gcs"] = {"ok": False, "error": gcs_err}

            if errors:
                raise HTTPException(status_code=503, detail=errors)
            return {"status": "ok", "db": "iam-connected", "gcs": bucket_name}

        return api
