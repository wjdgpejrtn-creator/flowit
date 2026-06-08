"""orchestrator — Main Orchestrator Modal app (REQ-004 §3.1).

LangGraphSupervisor(6노드)를 Modal ASGI app으로 노출.
api_server로부터 사용자 메시지를 받아 sub-agent(composer/skills/personalization)로
라우팅하고 SSE 스트림으로 응답.

Deploy:
    PYTHONUTF8=1 modal deploy services/agents/orchestrator/main.py

Health:
    curl https://flowit--orchestrator-orchestratoragent-fastapi.modal.run/v1/health

Secrets:
    GCP Secret Manager가 SSOT (2026-05-19 마이그레이션). Modal에 남는 secret은
    `cloudsql-iam-sa` 1개 — GCP ADC root credential. sub-agent URL + LLM URL은
    boot()에서 services.common.gcp_secrets.load_secrets_to_env로 런타임 pull.
"""
import asyncio

import modal

# fastapi는 modal.Image 안에만 install됨. GitHub Actions runner의 `modal deploy`
# CLI가 본 module을 import할 때는 미설치 → ModuleNotFoundError.
# 모든 fastapi 호출(FastAPI/Body/StreamingResponse)은 @modal.asgi_app()
# fastapi(self) 메서드 안에서만 evaluate되므로 (Python lazy method body),
# runner에서는 stub=None으로 충분.
try:
    from fastapi import Body, FastAPI
    from fastapi.responses import StreamingResponse
except ModuleNotFoundError:
    Body = FastAPI = None  # type: ignore[misc,assignment]
    StreamingResponse = None  # type: ignore[misc,assignment]

# composer drafter LLM은 50~70초 무프레임으로 도는 구간이 있다. 그동안 SSE가 하류(LB/브라우저)
# 에서 idle로 끊기면 프론트가 재연결→고착(노드 검색에서 멈춤)한다. → 무음마다 keepalive 주입.
_HEARTBEAT_SEC = 15.0
# api_server unwrap_agent_sse는 envelope의 frames[]만 통과시키므로 heartbeat도 frames에 프레임
# 1개가 필요하다. frontend SSE 파서는 미등록 frame_type을 default:break로 무시 → 표시/상태 무영향.
_HEARTBEAT_LINE = (
    'data: {"frames": [{"frame_type": "heartbeat"}], '
    '"state_delta": {}, "next_action": "continue"}\n\n'
)

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
        "google-cloud-storage>=2.10",  # GCSSessionFrameStore (재연결 복원 — 컨테이너 무관 공유 저장소)
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

        from ai_agent.adapters.agent_clients.http_sub_agent_client import HTTPSubAgentClient
        from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter
        from ai_agent.adapters.memory.gcs_session_frame_store import GCSSessionFrameStore
        from ai_agent.adapters.supervisor import LangGraphSupervisor
        from ai_agent.domain.services.intent_analyzer_service import IntentAnalyzerService

        from services.common.gcp_secrets import load_secrets_to_env

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
            "gcs-session-bucket":  "GCS_SESSION_BUCKET",  # GCSSessionFrameStore
        })

        llm = ModalLLMAdapter()

        # 세션 프레임 저장 = GCS 공유 저장소 (컨테이너 무관). supervisor가 스트림 종료 시
        # save_session()으로 전체 프레임을 저장 → 재연결/새로고침 GET이 어느 컨테이너로
        # 가든 load_frames()로 복원. (composer와 동일 GCS_SESSION_BUCKET·동일 스토어)
        # 과거 in-memory dict는 scale-to-zero/멀티컨테이너에서 404 유발 → 폐기.
        self._session_frame_store = GCSSessionFrameStore()

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
            session_frame_store=self._session_frame_store,
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
            session_id = req.session_id
            # 프레임 저장은 supervisor가 스트림 종료 시 GCSSessionFrameStore.save_session()으로
            # 일괄 수행 (boot에서 주입). 여기서 per-frame 누적 불필요.
            #
            # heartbeat 주의: wait_for를 제너레이터 __anext__에 직접 걸면 타임아웃 시 relay의
            # httpx read가 취소돼 스트림 자체가 깨진다. 그래서 프레임 생성은 producer 태스크가
            # 중단 없이 queue로 소진하고, 소비 루프는 queue.get()에만 타임아웃을 건다.

            async def generate():
                queue: asyncio.Queue = asyncio.Queue()

                async def _drain() -> None:
                    try:
                        async for frame in await self._graph.stream(
                            user_id=req.user_id,
                            session_id=session_id,
                            message=req.payload.get("message", ""),
                            trace_id=req.trace_id,
                            turn_count=req.state.turn_count,
                            round=req.payload.get("round", 1),
                            selected_skill_id=req.payload.get("selected_skill_id"),
                        ):
                            await queue.put(("frame", frame))
                    except Exception as exc:  # noqa: BLE001 — 소비 루프로 전달
                        await queue.put(("error", exc))
                    finally:
                        await queue.put(("done", None))

                producer = asyncio.create_task(_drain())
                try:
                    while True:
                        try:
                            kind, item = await asyncio.wait_for(
                                queue.get(), timeout=_HEARTBEAT_SEC
                            )
                        except TimeoutError:
                            yield _HEARTBEAT_LINE  # 무음 구간 keepalive
                            continue

                        if kind == "frame":
                            resp = AgentProtocolResponse(
                                frames=[item],
                                state_delta={},
                                next_action="continue",
                            )
                            yield f"data: {resp.model_dump_json()}\n\n"
                        elif kind == "error":
                            err = AgentProtocolResponse(
                                frames=[],
                                state_delta={"error": str(item)},
                                next_action="error",
                            )
                            yield f"data: {err.model_dump_json()}\n\n"
                            break
                        else:  # "done" — 정상 종료
                            break
                finally:
                    if not producer.done():
                        producer.cancel()

                done = AgentProtocolResponse(
                    frames=[],
                    state_delta={},
                    next_action="complete",
                )
                yield f"data: {done.model_dump_json()}\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")

        @api.get("/v1/agent/sessions/{session_id}/frames")
        async def get_session_frames(session_id: str, user_id: str = "") -> dict:
            """저장된 세션 프레임 반환 — 페이지 새로고침·재연결 복원용.

            GCSSessionFrameStore에서 조회 (컨테이너 무관). 인가는 GCS 경로가
            user_id로 스코프되어 자연 격리 — 타 유저 세션은 빈 배열. 미저장(진행 중·없음)
            도 빈 배열 + 200 → api_server가 E_FRAMES로 오해하지 않게 한다.
            """
            import uuid

            from fastapi import HTTPException

            try:
                sid = uuid.UUID(session_id)
                uid = uuid.UUID(user_id) if user_id else None
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"잘못된 파라미터: {exc}") from exc
            if uid is None:
                return {"frames": []}
            frames = await self._session_frame_store.load_frames(sid, uid)
            return {"frames": [f.model_dump(mode="json") for f in frames]}

        return api
