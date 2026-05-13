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

환경 변수 (Modal Secret 2개 마운트):

    agent-skills-builder-secret (sub-agent 담당자 박아름이 등록 — 5 키):
        LLM_BASE_URL                          llm-base ASGI base URL (예: https://...modal.run)
        EMBEDDING_BASE_URL                    BGE-M3 ASGI base URL (보통 LLM_BASE_URL과 동일)
        CLOUD_SQL_INSTANCE                    "<PROJECT>:<REGION>:<INSTANCE>" 형식
        DB_IAM_USER                           공용 SA 풀 이메일 (cloudsql-iam-modal@...)
        DB_NAME                               workflow_automation

    cloudsql-iam-sa (조장 1회 등록 — 1 키, 공용):
        GOOGLE_APPLICATION_CREDENTIALS_JSON   공용 GCP SA JSON key (cloud-sql-python-connector 인증용)

DB 접속: cloud-sql-python-connector + enable_iam_auth=True (DSN 패턴 금지 — 가이드
sub_agent_modal_deploy.md §3.2 + §5 참조).

박아름 룰:
- `BuildFromSOPUseCase` 실 endpoint 호출은 `llm-base`의 cls method 패턴 hotfix 필요
  (PR #39 후속, 신정혜 영역). 본 composition root는 시그니처 정합으로 wiring만 담당.
- ModalEmbeddingAdapter는 httpx 호출이라 즉시 동작.
- PgNodeDefinitionRepository는 황대원 5/15 PR에 머지된 구현체 그대로 사용.
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator, Literal

import modal


APP_NAME = "agent-skills-builder"


# ----------------------------------------------------------------------
# Pure helpers (modal runtime-free — integration 테스트에서 단독 호출)
# ----------------------------------------------------------------------


def _classify_next_action(frame: Any) -> Literal["continue", "complete", "error"]:
    """SSEFrame → AgentProtocolResponse.next_action 매핑.

    ResultFrame은 use case 정상 종료, ErrorFrame은 오류, 나머지(AgentNodeFrame
    등 진행 프레임)는 "continue". AgentProtocolResponse Literal 세 값 spec와 정합.
    """
    from common_schemas.transport import ErrorFrame, ResultFrame

    if isinstance(frame, ResultFrame):
        return "complete"
    if isinstance(frame, ErrorFrame):
        return "error"
    return "continue"


def _sse_bytes(response: Any) -> bytes:
    """AgentProtocolResponse → SSE 데이터 라인 (UTF-8 bytes).

    SSE 포맷: 'data: <json>\\n\\n'
    """
    body = response.model_dump_json()
    return f"data: {body}\n\n".encode("utf-8")


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
        # Cloud SQL IAM 인증 — google-cloud-sql-connector 만이 enable_iam_auth=True 지원
        "cloud-sql-python-connector[asyncpg]>=1.12",
    )
    # PYTHONPATH는 add_local_* 이전에 (build step) — modal SDK가 add_local_* 이후
    # build step을 거부하므로 add_local_dir 호출 전에 .env() 처리 필요.
    .env({
        "PYTHONPATH": ":".join([
            "/repo/packages/common_schemas/python",
            "/repo/modules",
        ]),
    })
    # 모노레포 소스 마운트 (Modal worker의 PYTHONPATH에 추가됨) — 마지막에 배치
    .add_local_dir("packages/common_schemas/python", "/repo/packages/common_schemas/python")
    .add_local_dir("modules/ai_agent", "/repo/modules/ai_agent")
    .add_local_dir("modules/nodes_graph", "/repo/modules/nodes_graph")
    .add_local_dir("modules/storage", "/repo/modules/storage")
)


app_secret = modal.Secret.from_name("agent-skills-builder-secret")
gcp_secret = modal.Secret.from_name("cloudsql-iam-sa")

app = modal.App(APP_NAME)


@app.cls(
    image=image,
    secrets=[app_secret, gcp_secret],
    timeout=600,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=8)
class SkillsBuilderAgent:
    """Skills Builder sub-agent — 3 use case 라우팅 + SSE 스트리밍."""

    @modal.enter()
    def boot(self) -> None:
        """어댑터 + Cloud SQL IAM Connector + session factory wiring.

        매 cold start에 한 번 실행. session_factory는 함수 단위로 새 session 생성
        (요청마다 격리). 어댑터와 connector는 worker 생애주기 동안 유지.

        DB 접속: cloud-sql-python-connector + enable_iam_auth=True (가이드
        sub_agent_modal_deploy.md §3.2 표준). DSN 패턴 금지.
        """
        import tempfile
        from pathlib import Path

        from google.cloud.sql.connector import Connector, IPTypes
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
        from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter

        # 1) GCP SA JSON을 임시 파일로 풀고 ADC 환경변수 지정
        sa_payload = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
        sa_path = Path(tempfile.gettempdir()) / "gcp-sa.json"
        sa_path.write_text(sa_payload, encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa_path)

        # 2) Cloud SQL Python Connector — IAM 인증 (비밀번호 없음)
        self._connector = Connector()

        async def _getconn():
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
            async_creator=_getconn,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        # 3) 어댑터 wiring (RPC LLM + HTTP embedding)
        self._llm = ModalLLMAdapter()  # MODAL_TOKEN_ID/SECRET + LLM_BASE_URL 환경변수 자동 사용
        self._embedder = ModalEmbeddingAdapter()  # EMBEDDING_BASE_URL 환경변수 자동 사용

    @modal.exit()
    def shutdown(self) -> None:
        """async engine + connector 정리 (sync 컨텍스트에서 호출)."""
        import asyncio

        if getattr(self, "_engine", None):
            asyncio.run(self._engine.dispose())
        if getattr(self, "_connector", None):
            asyncio.run(self._connector.close_async())

    @modal.asgi_app()
    def fastapi(self):
        from fastapi import Body, FastAPI, HTTPException
        from fastapi.responses import StreamingResponse

        from common_schemas.agent_protocol import AgentProtocolRequest

        api = FastAPI(title=APP_NAME, version="1.0")

        @api.get("/v1/health")
        async def health() -> dict[str, Any]:
            """어댑터 + Cloud SQL IAM 연결 헬스체크 (가이드 §3.3 패턴)."""
            from sqlalchemy import text

            errors: dict[str, str] = {}
            db_status: str = "iam-connected"

            # Cloud SQL IAM 연결 확인 — engine.connect() + SELECT 1
            try:
                async with self._engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            except Exception as exc:
                db_status = "error"
                errors["db"] = repr(exc)

            # 임베딩 endpoint base_url 설정 여부만 확인 (호출 X — endpoint 계약은 별도)
            try:
                _ = self._embedder._base_url
            except Exception as exc:
                errors["embedder"] = repr(exc)

            if errors:
                raise HTTPException(
                    status_code=503,
                    detail={"status": "degraded", "errors": errors},
                )
            return {"status": "ok", "app": APP_NAME, "db": db_status}

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
                yield _sse_bytes(
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
                    yield _sse_bytes(
                        AgentProtocolResponse(
                            frames=[frame],
                            state_delta={},
                            next_action=_classify_next_action(frame),
                        )
                    )

                # use case 정상 종료 — repo.upsert()로 발생한 변경 commit
                await session.commit()
            except Exception:
                # use case 내부 예외 → rollback (격리 정책으로 잡히지 않은 케이스)
                await session.rollback()
                raise
