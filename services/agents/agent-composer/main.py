"""agent-composer — Workflow Composer Modal app (REQ-004 §3.2).

LangGraphOrchestrator(16노드)를 Modal ASGI app으로 노출.
Orchestrator로부터 AgentProtocolRequest를 받아 SSE 스트림으로 응답.

Deploy:
    PYTHONUTF8=1 modal deploy services/agents/agent-composer/main.py

Health:
    curl https://dhwang0803--agent-composer-agentcomposer-fastapi.modal.run/v1/health

Secrets:
    GCP Secret Manager가 SSOT (2026-05-19 마이그레이션). Modal에 남는 secret은
    `cloudsql-iam-sa` 1개 — GCP ADC root credential. 나머지 환경변수는 boot()
    에서 services.common.gcp_secrets.load_secrets_to_env로 런타임 pull한다.
"""
import os

import modal
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

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
        "google-cloud-secret-manager>=2.20",
        "google-cloud-storage>=2.0",
    )
    .env({
        "PYTHONPATH": "/app/modules:/app/common_schemas_src:/repo",
        "GOOGLE_CLOUD_PROJECT": "<GCP_PROJECT_ID>",
    })
    .add_local_dir("modules", remote_path="/app/modules")
    .add_local_dir("packages/common_schemas/python", remote_path="/app/common_schemas_src")
    .add_local_dir("services/common", remote_path="/repo/services/common")
)

app = modal.App("agent-composer")


@app.cls(
    image=image,
    secrets=[gcp_secret],
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

        from services.common.gcp_secrets import load_secrets_to_env

        # 1) GCP SA JSON → 임시 파일 → ADC 환경변수
        sa_payload = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
        sa_path = Path(tempfile.gettempdir()) / "gcp-sa.json"
        sa_path.write_text(sa_payload, encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa_path)

        # 2) GCP Secret Manager → 환경변수 주입
        load_secrets_to_env({
            "cloud-sql-instance":    "CLOUD_SQL_INSTANCE",
            "db-iam-user":           "DB_IAM_USER",
            "db-name":               "DB_NAME",
            "llm-base-url":          "LLM_BASE_URL",
            "embedding-base-url":    "EMBEDDING_BASE_URL",
            "gcs-session-bucket":    "GCS_SESSION_BUCKET",
            "execution-engine-url":  "EXECUTION_ENGINE_URL",
        })
        # gcs-personal-bucket: secret 미등록이어도 composer boot 실패 방지 (PR #171 패턴)
        try:
            load_secrets_to_env({"gcs-personal-bucket": "GCS_PERSONAL_BUCKET"})
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "gcs-personal-bucket secret 미등록 — personal memory 비활성: %s", exc
            )

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
        from ai_agent.adapters.memory.gcs_session_frame_store import GCSSessionFrameStore
        from ai_agent.adapters.memory.gcs_workflow_draft_store import GCSWorkflowDraftStore
        from ai_agent.adapters.memory.gcs_memory_store import GCSMemoryStore
        from ai_agent.adapters.node_registry_adapter import NodeRegistryAdapter
        from ai_agent.adapters.langgraph.composer_graph import LangGraphOrchestrator
        from ai_agent.application.agents.workflow_composer.approve_workflow_use_case import ApproveWorkflowUseCase
        from ai_agent.domain.services.intent_analyzer_service import IntentAnalyzerService
        from ai_agent.domain.services.drafter_service import DrafterService
        from ai_agent.domain.services.qa_evaluator_service import QAEvaluatorService
        from ai_agent.domain.services.slot_filling_service import SlotFillingService
        from ai_agent.domain.services.workflow_diff_service import WorkflowDiffService
        from nodes_graph.domain.services.graph_validator import GraphValidator
        from storage.repositories.pg_node_definition_repository import PgNodeDefinitionRepository
        from storage.repositories.pg_workflow_repository import PgWorkflowRepository

        llm = ModalLLMAdapter()
        embedder = ModalEmbeddingAdapter()

        self._node_repo_cls = PgNodeDefinitionRepository
        self._workflow_repo_cls = PgWorkflowRepository
        self._embedder = embedder
        self._node_registry_cls = NodeRegistryAdapter
        self._graph_validator_cls = GraphValidator
        self._intent_analyzer = IntentAnalyzerService(llm)
        self._drafter = DrafterService(llm)
        self._qa_evaluator = QAEvaluatorService(llm)
        self._slot_filler = SlotFillingService()
        self._llm = llm
        self._orchestrator_cls = LangGraphOrchestrator
        self._session_frame_store = GCSSessionFrameStore()
        self._workflow_draft_store = GCSWorkflowDraftStore()
        self._personal_memory_store = GCSMemoryStore()
        self._diff_service = WorkflowDiffService()
        self._execution_engine_url = os.getenv("EXECUTION_ENGINE_URL", "")

        # 그래프는 요청마다 세션을 새로 생성해서 주입 — _get_graph() 참조

    @modal.exit()
    def shutdown(self) -> None:
        import asyncio
        if getattr(self, "_engine", None):
            asyncio.run(self._engine.dispose())
        if getattr(self, "_connector", None):
            asyncio.run(self._connector.close_async())

    @modal.asgi_app()
    def fastapi(self):
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
        async def route(req: AgentProtocolRequest = Body(...)):
            async def generate():
                try:
                    async with self._session_factory() as session:
                        node_repo = self._node_repo_cls(session)
                        workflow_repo = self._workflow_repo_cls(session)
                        node_registry = self._node_registry_cls(node_repo, self._embedder)
                        graph_validator = self._graph_validator_cls(node_repo)
                        graph = self._orchestrator_cls(
                            intent_analyzer=self._intent_analyzer,
                            drafter=self._drafter,
                            qa_evaluator=self._qa_evaluator,
                            slot_filler=self._slot_filler,
                            node_registry=node_registry,
                            workflow_repo=workflow_repo,
                            graph_validator=graph_validator,
                            session_frame_store=self._session_frame_store,
                            llm=self._llm,
                            workflow_draft_store=self._workflow_draft_store,
                            execution_engine_url=self._execution_engine_url,
                            personal_memory_store=self._personal_memory_store,
                        )
                        async for frame in await graph.stream(
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

        @api.post("/v1/agent/approve")
        async def approve(body: dict = Body(...)):
            """사용자 승인 이벤트 처리 — WorkflowDiff 계산 후 Personalization 전달.

            Request body:
                session_id: str
                user_id:    str
                workflow_id: str
            """
            import uuid
            from ai_agent.application.agents.workflow_composer.approve_workflow_use_case import ApproveWorkflowUseCase

            try:
                session_id = uuid.UUID(body["session_id"])
                user_id    = uuid.UUID(body["user_id"])
                workflow_id = uuid.UUID(body["workflow_id"])
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=f"잘못된 파라미터: {exc}") from exc

            async with self._session_factory() as session:
                workflow_repo = self._workflow_repo_cls(session)
                use_case = ApproveWorkflowUseCase(
                    workflow_draft_store=self._workflow_draft_store,
                    workflow_repo=workflow_repo,
                    diff_service=self._diff_service,
                    personalization_client=None,  # TODO: PersonalizationClient 주입
                )
                diff = await use_case.execute(session_id, user_id, workflow_id)

            if diff is None:
                return {"status": "no_draft", "diff": None}
            return {
                "status": "ok",
                "diff": {
                    "added_nodes": len(diff.added_nodes),
                    "removed_nodes": len(diff.removed_nodes),
                    "modified_params": len(diff.modified_params),
                    "feedback_lines": diff.to_feedback_lines(),
                },
            }

        @api.get("/v1/agent/sessions")
        async def list_sessions(user_id: str, limit: int = 20):
            """세션 목록 조회 — 최신순.

            Query params:
                user_id: str (UUID)
                limit:   int (default 20, max 100)
            """
            import uuid

            try:
                uid = uuid.UUID(user_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"잘못된 user_id: {exc}") from exc

            limit = min(max(limit, 1), 100)
            refs = await self._session_frame_store.list_sessions(uid, limit=limit)
            return {
                "sessions": [r.model_dump(mode="json") for r in refs],
                "count": len(refs),
            }

        @api.get("/v1/agent/sessions/{session_id}/frames")
        async def get_session_frames(session_id: str, user_id: str):
            """세션 SSE 프레임 전체 조회.

            Path params:
                session_id: str (UUID)
            Query params:
                user_id: str (UUID)
            """
            import uuid

            try:
                sid = uuid.UUID(session_id)
                uid = uuid.UUID(user_id)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"잘못된 파라미터: {exc}") from exc

            frames = await self._session_frame_store.load_frames(sid, uid)
            return {
                "session_id": session_id,
                "frames": [f.model_dump(mode="json") for f in frames],
                "count": len(frames),
            }

        return api
