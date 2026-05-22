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
            sop은 payload.step ∈ {"extract", "confirm"} 추가 (wizard 2단계, ADR-0020 Q8 / 기본 extract)
        → 분기:
            "sop" + step=extract → BuildFromSOPUseCase.extract_draft(user_id, document, personal_memory)
            "sop" + step=confirm → BuildFromSOPUseCase.confirm(user_id, skills)
            "industry_default"   → BuildFromIndustryDefaultUseCase.execute(user_id, industry_code)
            "functional_domain"  → BuildFromFunctionalDomainUseCase.execute(user_id, domain_code)
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
import os
from collections.abc import AsyncIterator
from typing import Any, Literal

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
    return f"data: {body}\n\n".encode()


def _done_frame_bytes() -> bytes:
    """SSE 스트림 종결 시그널 — frames=[], next_action='complete'.

    2026-05-14 결정: dual 종결 패턴 채택 (agent-composer/orchestrator와 통일).
    모든 종결 path(정상 종료 / use case 내부 예외 / unsupported source_type)에서
    마지막 frame으로 발송. frontend는 이 frame을 받으면 스트림 종료로 간주한다.
    """
    from common_schemas.agent_protocol import AgentProtocolResponse

    return _sse_bytes(
        AgentProtocolResponse(
            frames=[],
            state_delta={},
            next_action="complete",
        )
    )


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
        # GCP Secret Manager (런타임 secret pull, 2026-05-19 마이그레이션)
        "google-cloud-secret-manager>=2.20",
        # Transitive: storage.mappers → toolset.runtime_validator → import jsonschema.
        # 박아름 use case가 toolset 직접 사용 안 하지만 storage import 체인으로 끌려옴.
        "jsonschema>=4.0",
        # 가이드 §5 함정 표 — protobuf 버전 핀 (cloud-sql-python-connector 호환)
        "protobuf>=4.25",
    )
    # PYTHONPATH는 add_local_* 이전에 (build step) — modal SDK가 add_local_* 이후
    # build step을 거부하므로 add_local_dir 호출 전에 .env() 처리 필요.
    .env({
        "PYTHONPATH": ":".join([
            "/repo/packages/common_schemas/python",
            "/repo/modules",
            "/repo",
        ]),
        "GOOGLE_CLOUD_PROJECT": "<GCP_PROJECT_ID>",
    })
    # 모노레포 소스 마운트 (Modal worker의 PYTHONPATH에 추가됨) — 마지막에 배치
    .add_local_dir("packages/common_schemas/python", "/repo/packages/common_schemas/python")
    # modules 전체 통째 마운트 — storage가 auth/toolset/doc_parser 등 거의 모든 도메인을
    # transitive import하므로 개별 add_local_dir 대신 한 번에 마운트 (가이드 함정 회피).
    .add_local_dir("modules", "/repo/modules")
    # services.common.gcp_secrets 헬퍼 — GCP Secret Manager 런타임 pull용
    .add_local_dir("services/common", "/repo/services/common")
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
class SkillsBuilderAgent:
    """Skills Builder sub-agent — 3 use case 라우팅 + SSE 스트리밍."""

    @modal.enter()
    def boot(self) -> None:
        """sync 초기화 — ADC + 어댑터 + DB resources(instance-scoped) wiring.

        Cloud SQL Connector는 `getconn()` 안에서 lazy 초기화 + 명시적 loop
        바인딩 패턴 적용 (신정혜 PR #56 commit `6390a43`, 2026-05-14 채택).

        Modal asgi_app은 같은 instance가 받는 모든 request에 같은 event loop를
        재사용한다. 첫 request 시점에 Connector를 만들면 그 loop가 짝꿍으로
        등록되어 이후 request도 동일 loop라 ConnectorLoopError 발생 안 함.
        boot()의 sync loop와는 분리되어 있어도 정합.
        """
        import tempfile
        from pathlib import Path

        from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
        from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from services.common.gcp_secrets import load_secrets_to_env

        # 1) GCP SA JSON을 임시 파일로 풀고 ADC 환경변수 지정
        sa_payload = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
        sa_path = Path(tempfile.gettempdir()) / "gcp-sa.json"
        sa_path.write_text(sa_payload, encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa_path)

        # 2) GCP Secret Manager → 환경변수 주입
        load_secrets_to_env({
            "cloud-sql-instance": "CLOUD_SQL_INSTANCE",
            "db-iam-user":        "DB_IAM_USER",
            "db-name":            "DB_NAME",
            "llm-base-url":       "LLM_BASE_URL",
            "embedding-base-url": "EMBEDDING_BASE_URL",
        })

        # 2) 어댑터 wiring (RPC LLM + HTTP embedding) — async 의존 없음
        self._llm = ModalLLMAdapter()
        self._embedder = ModalEmbeddingAdapter()

        # 3) Cloud SQL Connector — getconn() 안에서 lazy 초기화 + loop 명시 바인딩
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

    @modal.exit()
    def shutdown(self) -> None:
        """Modal exit hook — instance-scoped DB resources cleanup."""
        import asyncio

        if getattr(self, "_engine", None):
            asyncio.run(self._engine.dispose())
        if getattr(self, "_connector", None):
            asyncio.run(self._connector.close_async())

    @modal.asgi_app()
    def fastapi(self):

        from common_schemas.agent_protocol import AgentProtocolRequest
        from fastapi import Body, FastAPI, HTTPException
        from fastapi.responses import StreamingResponse

        api = FastAPI(title=APP_NAME, version="1.0")

        @api.get("/v1/health")
        async def health() -> dict[str, Any]:
            """어댑터 + Cloud SQL IAM 연결 헬스체크.

            instance-scoped self._engine 사용 — 첫 request 시점에 Connector가
            running loop를 짝꿍으로 등록하므로 충돌 없음 (boot() docstring 참조).
            예외는 logger.warning으로만 내부 기록, detail은 마스킹된 메시지만 노출.
            """
            import logging

            from sqlalchemy import text

            logger = logging.getLogger(__name__)
            errors: dict[str, str] = {}

            try:
                async with self._engine.connect() as conn:
                    row = await conn.scalar(text("SELECT 1"))
                if row != 1:
                    raise RuntimeError(f"SELECT 1 returned {row!r}")
            except Exception as exc:
                logger.warning("db unreachable: %s", repr(exc))
                errors["db"] = "unreachable"

            try:
                _ = self._embedder._base_url
            except Exception as exc:
                logger.warning("embedder unconfigured: %s", repr(exc))
                errors["embedder"] = "unconfigured"

            if errors:
                raise HTTPException(
                    status_code=503,
                    detail={"status": "degraded", "errors": errors},
                )
            return {"status": "ok", "app": APP_NAME, "db": "iam-connected"}

        @api.post("/v1/agent/route")
        async def route(req: AgentProtocolRequest = Body(...)) -> StreamingResponse:
            """AgentProtocolRequest → source_type 분기 → SSE 스트리밍.

            HTTPSubAgentClient.send()와 짝을 이루는 endpoint. 응답은 SSE 텍스트
            스트림 ("data: <json>\\n\\n"). 각 SSEFrame을 AgentProtocolResponse로
            래핑해서 직렬화. DB session은 _stream 내부에서 instance-scoped
            self._session_factory()로 생성.
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
        from ai_agent.application.agents.skills_builder.build_from_functional_domain_use_case import (
            BuildFromFunctionalDomainUseCase,
        )
        from ai_agent.application.agents.skills_builder.build_from_industry_default_use_case import (
            BuildFromIndustryDefaultUseCase,
        )
        from ai_agent.application.agents.skills_builder.build_from_sop_use_case import (
            BuildFromSOPUseCase,
        )
        from common_schemas import DocumentBlock
        from common_schemas.agent_protocol import AgentProtocolResponse
        from common_schemas.transport import ErrorFrame
        from skills_marketplace.application.use_cases import CreateDraftSkillUseCase
        from storage.repositories.pg_marketplace_skill_repository import PgMarketplaceSkillRepository
        from storage.repositories.pg_node_definition_repository import PgNodeDefinitionRepository

        # AgentProtocolRequest 필드: session_id/user_id/state/personal_memory는 top-level,
        # source_type별 추가 입력은 payload(자유 dict)에서 추출.
        payload = req.payload or {}
        source_type = payload.get("source_type")

        # instance-scoped session_factory 사용 — boot()에서 미리 생성됨
        # (신정혜 PR #56 commit 6390a43 패턴, 2026-05-14)
        async with self._session_factory() as session:
            repo = PgNodeDefinitionRepository(session)

            if source_type == "industry_default":
                use_case = BuildFromIndustryDefaultUseCase(repo, self._embedder)
                stream = use_case.execute(req.user_id, payload["industry_code"])
            elif source_type == "functional_domain":
                use_case = BuildFromFunctionalDomainUseCase(repo, self._embedder)
                stream = use_case.execute(req.user_id, payload["domain_code"])
            elif source_type == "sop":
                # wizard 2단계(ADR-0020 Q8): extract_draft(추출·검토용, 저장X) / confirm(편집→DRAFT).
                # confirm은 CreateDraftSkillUseCase(SkillRepository=PgMarketplaceSkillRepository, PR #147) 경유.
                use_case = BuildFromSOPUseCase(
                    CreateDraftSkillUseCase(PgMarketplaceSkillRepository(session)),
                    self._embedder,
                    self._llm,
                )
                step = payload.get("step", "extract")
                if step == "extract":
                    document = DocumentBlock.model_validate(payload["document"])
                    stream = use_case.extract_draft(req.user_id, document, req.personal_memory)
                elif step == "confirm":
                    stream = use_case.confirm(req.user_id, payload["skills"])
                else:
                    yield _sse_bytes(
                        AgentProtocolResponse(
                            frames=[],
                            state_delta={"error": "E_SOP_STEP_INVALID", "step": step},
                            next_action="error",
                        )
                    )
                    yield _done_frame_bytes()
                    return
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
                yield _done_frame_bytes()  # 2026-05-14: dual 종결 패턴
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
                yield _done_frame_bytes()  # 2026-05-14: dual 종결 패턴
            except Exception as exc:
                # use case 내부 예외 → rollback + ErrorFrame + done frame
                # (2026-05-14: dual 종결 패턴 — raise 대신 명시 발송으로 contract 보장)
                await session.rollback()
                yield _sse_bytes(
                    AgentProtocolResponse(
                        frames=[ErrorFrame(code="E_INTERNAL", message=str(exc))],
                        state_delta={},
                        next_action="error",
                    )
                )
                yield _done_frame_bytes()
                return
