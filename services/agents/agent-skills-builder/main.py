"""agent-skills-builder — Modal app for Skills Builder sub-agent (REQ-004).

박아름 Skills Builder sub-agent의 Modal app composition root. Main Orchestrator
(`orchestrator` Modal app)가 VPC 내부 HTTP로 호출한다.

Layout:
- `image`: debian_slim + ai_agent / nodes_graph / storage / common_schemas 모듈 마운트.
  GPU 없음 — LLM/Embedding은 `llm-base` Modal app endpoint를 HTTP로 호출하는
  클라이언트 패턴.
- `SkillsBuilderAgent` @cls: @enter()에서 어댑터 + repo + 3 use case wiring,
  @asgi_app()으로 `/v1/agent/route` (AgentProtocolRequest SSE) 노출.

routing:
    POST /v1/agent/route
        body: AgentProtocolRequest
            payload.source_type ∈ {"sop", "industry_default", "functional_domain"}
        → 분기:
            "sop"               → BuildFromSOPUseCase.execute(user_id, document, personal_memory)
            "industry_default"  → BuildFromIndustryDefaultUseCase.execute(user_id, industry_code)
            "functional_domain" → BuildFromFunctionalDomainUseCase.execute(user_id, domain_code)
        → 각 use case가 AsyncGenerator[SSEFrame] yield
        → SSE 텍스트 스트림 ("data: <json>\\n\\n") 으로 변환해 응답
    GET /v1/health
        어댑터 + DB 연결 헬스체크. 503 on degrade.

deploy:
    PYTHONUTF8=1 modal deploy services/agents/agent-skills-builder/main.py

환경 변수 (Modal Secret):
    MODAL_TOKEN_ID / MODAL_TOKEN_SECRET  — Modal RPC 인증 (ModalLLMAdapter 사용)
    LLM_BASE_URL                          — llm-base ASGI base URL (예: https://...modal.run)
    EMBEDDING_BASE_URL                    — llm-base BGE-M3 endpoint base URL (보통 LLM_BASE_URL과 동일)
    DATABASE_URL                          — PostgreSQL DSN (postgresql+asyncpg://...)

박아름 룰:
- `BuildFromSOPUseCase` 실 endpoint 호출은 `llm-base`의 cls method 패턴 hotfix 필요
  (PR #39 후속, 신정혜 영역). 본 composition root는 시그니처 정합으로 wiring만 담당.
- ModalEmbeddingAdapter는 httpx 호출이라 즉시 동작.
- PgNodeDefinitionRepository는 황대원 5/15 PR에 머지된 구현체 그대로 사용.
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import modal


APP_NAME = "agent-skills-builder"


image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        # Web layer
        "fastapi>=0.115",
        "httpx>=0.27",
        # Domain / common
        "pydantic>=2.13",
        # Storage (PgNodeDefinitionRepository 의존)
        "sqlalchemy[asyncio]>=2.0",
        "asyncpg>=0.30",
        "pgvector>=0.3",
    )
    # 모노레포 소스 마운트 (Modal worker의 PYTHONPATH에 추가됨)
    .add_local_dir("packages/common_schemas/python", "/repo/packages/common_schemas/python")
    .add_local_dir("modules/ai_agent", "/repo/modules/ai_agent")
    .add_local_dir("modules/nodes_graph", "/repo/modules/nodes_graph")
    .add_local_dir("modules/storage", "/repo/modules/storage")
    .env({
        "PYTHONPATH": ":".join([
            "/repo/packages/common_schemas/python",
            "/repo/modules",
        ]),
    })
)


modal_secret = modal.Secret.from_name("agent-skills-builder-secret")

app = modal.App(APP_NAME)


@app.cls(
    image=image,
    secrets=[modal_secret],
    timeout=600,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=8)
class SkillsBuilderAgent:
    """Skills Builder sub-agent — 3 use case 라우팅 + SSE 스트리밍."""

    @modal.enter()
    def boot(self) -> None:
        """어댑터 + repo + use case wiring.

        매 cold start에 한 번 실행. session_factory는 함수 단위로 새 session 생성
        (요청마다 격리). 어댑터는 worker 생애주기 동안 유지.
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
        from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter

        # --- 어댑터 ---
        self._llm = ModalLLMAdapter()  # MODAL_TOKEN_ID/SECRET + LLM_BASE_URL 환경변수 자동 사용
        self._embedder = ModalEmbeddingAdapter()  # EMBEDDING_BASE_URL 환경변수 자동 사용

        # --- DB engine + session factory ---
        database_url = os.environ["DATABASE_URL"]
        self._engine = create_async_engine(database_url, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    @modal.exit()
    def shutdown(self) -> None:
        if getattr(self, "_engine", None):
            # async dispose 필요 — sync 컨텍스트에서 호출이라 sync_engine.dispose() 패턴
            self._engine.sync_engine.dispose()

    @modal.asgi_app()
    def fastapi(self):
        from fastapi import Body, FastAPI, HTTPException
        from fastapi.responses import StreamingResponse

        from common_schemas.agent_protocol import AgentProtocolRequest

        api = FastAPI(title=APP_NAME, version="1.0")

        @api.get("/v1/health")
        async def health() -> dict[str, Any]:
            """어댑터 + DB 연결 헬스체크."""
            errors: dict[str, str] = {}

            # DB 연결 확인 — session 짧게 열어서 SELECT 1
            try:
                async with self._session_factory() as session:
                    await session.execute(__import__("sqlalchemy").text("SELECT 1"))
            except Exception as exc:
                errors["db"] = repr(exc)

            # 임베딩 endpoint 확인 (선택)
            try:
                # ModalEmbeddingAdapter._client으로 health 호출하기엔 endpoint 계약 미정
                # → 본 단계에서는 base_url 설정 여부만 확인
                _ = self._embedder._base_url
            except Exception as exc:
                errors["embedder"] = repr(exc)

            if errors:
                raise HTTPException(
                    status_code=503,
                    detail={"status": "degraded", "errors": errors},
                )
            return {"status": "ok", "app": APP_NAME}

        @api.post("/v1/agent/route")
        async def route(req: AgentProtocolRequest = Body(...)) -> StreamingResponse:
            """AgentProtocolRequest → source_type 분기 → SSE 스트리밍.

            HTTPSubAgentClient.send()와 짝을 이루는 endpoint. 응답은 SSE 텍스트
            스트림 ("data: <json>\\n\\n"). 각 SSEFrame을 AgentProtocolResponse로
            래핑해서 직렬화.
            """
            return StreamingResponse(
                self._stream(req),
                media_type="text/event-stream",
            )

        return api

    # ------------------------------------------------------------------
    # Internals — 라우팅 + SSE 직렬화
    # ------------------------------------------------------------------

    async def _stream(self, req: Any) -> AsyncIterator[bytes]:
        """source_type 분기 → use case 호출 → SSE 이벤트 yield.

        각 SSEFrame을 `AgentProtocolResponse(frames=[frame], next_action=...)`
        로 래핑. next_action은 ResultFrame에서 "complete", ErrorFrame에서
        "error", 중간 진행 프레임에서 "continue"로 설정 (Literal 세 값 spec).
        """
        from common_schemas import DocumentBlock
        from common_schemas.agent_protocol import AgentProtocolResponse
        from common_schemas.transport import ErrorFrame, ResultFrame

        from ai_agent.application.agents.skills_builder.build_from_functional_domain_use_case import (
            BuildFromFunctionalDomainUseCase,
        )
        from ai_agent.application.agents.skills_builder.build_from_industry_default_use_case import (
            BuildFromIndustryDefaultUseCase,
        )
        from ai_agent.application.agents.skills_builder.build_from_sop_use_case import (
            BuildFromSOPUseCase,
        )
        from storage.repositories.pg_node_definition_repository import PgNodeDefinitionRepository

        # AgentProtocolRequest 필드: session_id/user_id/state/personal_memory는 top-level,
        # source_type별 추가 입력은 payload(자유 dict)에서 추출.
        payload = req.payload or {}
        source_type = payload.get("source_type")

        # 요청 단위 session — use case 실행 동안 살아있어야 함
        async with self._session_factory() as session:
            repo = PgNodeDefinitionRepository(session)

            if source_type == "industry_default":
                use_case = BuildFromIndustryDefaultUseCase(repo, self._embedder)
                stream = use_case.execute(req.user_id, payload["industry_code"])
            elif source_type == "functional_domain":
                use_case = BuildFromFunctionalDomainUseCase(repo, self._embedder)
                stream = use_case.execute(req.user_id, payload["domain_code"])
            elif source_type == "sop":
                use_case = BuildFromSOPUseCase(repo, self._embedder, self._llm)
                document = DocumentBlock.model_validate(payload["document"])
                stream = use_case.execute(req.user_id, document, req.personal_memory)
            else:
                yield self._sse_bytes(
                    AgentProtocolResponse(
                        frames=[],
                        state_delta={
                            "error": "E_SOURCE_TYPE_UNSUPPORTED",
                            "source_type": source_type,
                        },
                        next_action="error",
                    )
                )
                return

            try:
                async for frame in stream:
                    if isinstance(frame, ResultFrame):
                        next_action = "complete"
                    elif isinstance(frame, ErrorFrame):
                        next_action = "error"
                    else:
                        next_action = "continue"

                    yield self._sse_bytes(
                        AgentProtocolResponse(
                            frames=[frame],
                            state_delta={},
                            next_action=next_action,
                        )
                    )

                # use case 정상 종료 — repo.upsert()로 발생한 변경 commit
                await session.commit()
            except Exception:
                # use case 내부 예외 → rollback (격리 정책으로 잡히지 않은 케이스)
                await session.rollback()
                raise

    @staticmethod
    def _sse_bytes(response: Any) -> bytes:
        """AgentProtocolResponse → SSE 데이터 라인 (UTF-8 bytes).

        SSE 포맷: 'data: <json>\\n\\n'
        """
        body = response.model_dump_json()
        return f"data: {body}\n\n".encode("utf-8")
