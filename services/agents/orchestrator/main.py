"""orchestrator — Main Orchestrator Modal app (REQ-004 §3.1).

LangGraphSupervisor(6노드)를 Modal ASGI app으로 노출.
api_server로부터 사용자 메시지를 받아 sub-agent(composer/skills/personalization)로
라우팅하고 SSE 스트림으로 응답.

Deploy:
    PYTHONUTF8=1 modal deploy services/agents/orchestrator/main.py

Health:
    curl https://<WORKSPACE>--orchestrator.modal.run/v1/health

Sub-agent URL 환경변수 (agent-orchestrator-secret):
    COMPOSER_URL, SKILLS_BUILDER_URL, PERSONALIZATION_URL
"""
from __future__ import annotations

import modal
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app_secret = modal.Secret.from_name("agent-orchestrator-secret")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi>=0.115",
        "httpx>=0.27",
        "pydantic>=2.13",
        "langgraph>=0.2",
        "modal>=0.73",
    )
    .env({"PYTHONPATH": "/app/modules:/app/common_schemas_src"})
    .add_local_dir("modules", remote_path="/app/modules")
    .add_local_dir("packages/common_schemas/python", remote_path="/app/common_schemas_src")
)

app = modal.App("orchestrator")


@app.cls(
    image=image,
    secrets=[app_secret],
    timeout=600,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=8)
class OrchestratorAgent:
    """Main Orchestrator — LangGraphSupervisor(6노드) composition root."""

    @modal.enter()
    def boot(self) -> None:
        import os

        from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter
        from ai_agent.adapters.agent_clients.http_sub_agent_client import HTTPSubAgentClient
        from ai_agent.adapters.langgraph.supervisor_graph import LangGraphSupervisor
        from ai_agent.domain.services.intent_analyzer_service import IntentAnalyzerService

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
        )

    @modal.asgi_app()
    def fastapi(self):
        from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse

        api = FastAPI(title="orchestrator", version="1.0")

        @api.get("/v1/health")
        async def health() -> dict[str, object]:
            return {"status": "ok"}

        @api.post("/v1/agent/route")
        async def route(request: Request):
            req = AgentProtocolRequest.model_validate(await request.json())
            async def generate():
                try:
                    async for frame in await self._graph.stream(
                        user_id=req.user_id,
                        session_id=req.session_id,
                        message=req.payload.get("message", ""),
                        trace_id=req.trace_id,
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
