"""orchestrator — Main Orchestrator Modal app (REQ-004 §3.1).

LangGraphSupervisor(6노드)를 Modal ASGI app으로 노출.
api_server로부터 사용자 메시지를 받아 sub-agent(composer/skills/personalization)로
라우팅하고 SSE 스트림으로 응답.

Deploy:
    PYTHONUTF8=1 modal deploy services/agents/orchestrator/main.py

Health:
    curl https://<WORKSPACE>--orchestrator.modal.run/v1/health

Secrets:
    GCP Secret Manager가 SSOT (2026-05-19 마이그레이션). Modal에 남는 secret은
    `cloudsql-iam-sa` 1개 — GCP ADC root credential. sub-agent URL + LLM URL은
    boot()에서 services.common.gcp_secrets.load_secrets_to_env로 런타임 pull.
"""
import modal
from fastapi import Body, FastAPI
from fastapi.responses import StreamingResponse

gcp_secret = modal.Secret.from_name("cloudsql-iam-sa")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi>=0.115",
        "httpx>=0.27",
        "pydantic>=2.13",
        "langgraph>=0.2",
        "modal>=0.73",
        "google-cloud-secret-manager>=2.20",
    )
    .env({
        "PYTHONPATH": "/app/modules:/app/common_schemas_src:/repo",
        "GOOGLE_CLOUD_PROJECT": "<GCP_PROJECT_ID>",
    })
    .add_local_dir("modules", remote_path="/app/modules")
    .add_local_dir("packages/common_schemas/python", remote_path="/app/common_schemas_src")
    .add_local_dir("services/common", remote_path="/repo/services/common")
)

app = modal.App("orchestrator")


@app.cls(
    image=image,
    secrets=[gcp_secret],
    timeout=600,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=8)
class OrchestratorAgent:
    """Main Orchestrator — LangGraphSupervisor(6노드) composition root."""

    @modal.enter()
    def boot(self) -> None:
        import os
        import tempfile
        from pathlib import Path

        from services.common.gcp_secrets import load_secrets_to_env

        from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter
        from ai_agent.adapters.agent_clients.http_sub_agent_client import HTTPSubAgentClient
        from ai_agent.adapters.langgraph.supervisor_graph import LangGraphSupervisor
        from ai_agent.domain.services.intent_analyzer_service import IntentAnalyzerService

        # GCP SA JSON → 임시 파일 → ADC 환경변수
        sa_payload = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
        sa_path = Path(tempfile.gettempdir()) / "gcp-sa.json"
        sa_path.write_text(sa_payload, encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa_path)

        # GCP Secret Manager → 환경변수 주입
        load_secrets_to_env({
            "composer-url":        "COMPOSER_URL",
            "skills-builder-url":  "SKILLS_BUILDER_URL",
            "personalization-url": "PERSONALIZATION_URL",
            "llm-base-url":        "LLM_BASE_URL",  # ModalLLMAdapter HTTP fallback
        })

        llm = ModalLLMAdapter()

        self._graph = LangGraphSupervisor(
            intent_analyzer=IntentAnalyzerService(llm),
            personalization_client=HTTPSubAgentClient(
                base_url=os.environ["PERSONALIZATION_URL"]
            ),
            composer_client=HTTPSubAgentClient(
                base_url=os.environ["COMPOSER_URL"]
            ),
            skills_client=HTTPSubAgentClient(
                base_url=os.environ["SKILLS_BUILDER_URL"]
            ),
            llm=llm,
        )

    @modal.asgi_app()
    def fastapi(self):
        from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse

        api = FastAPI(title="orchestrator", version="1.0")

        @api.get("/v1/health")
        async def health() -> dict[str, object]:
            return {"status": "ok"}

        @api.post("/v1/agent/route")
        async def route(req: AgentProtocolRequest = Body(...)):
            async def generate():
                try:
                    async for frame in await self._graph.stream(
                        user_id=req.user_id,
                        session_id=req.session_id,
                        message=req.payload.get("message", ""),
                        trace_id=req.trace_id,
                        turn_count=req.state.turn_count,
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
