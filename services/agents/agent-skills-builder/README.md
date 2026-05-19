# agent-skills-builder — Modal app 배포 가이드

> **REQ-004 §2.3** — 박아름 Skills Builder sub-agent. Main Orchestrator(`orchestrator` Modal app)가 VPC 내부 HTTP로 호출하면 `BuildFromSOPUseCase` / `BuildFromIndustryDefaultUseCase` / `BuildFromFunctionalDomainUseCase` 3 use case로 분기 라우팅하고, 결과를 SSE 스트리밍한다.
>
> CPU only — LLM / Embedding은 `llm-base` Modal app endpoint를 HTTP/RPC로 호출하는 클라이언트 패턴. GPU 점유 없음.

## 사전 체크

- [ ] Modal 계정 + dhwang0803 워크스페이스 권한 (조장에게 요청)
- [ ] `.env` 파일 프로젝트 루트에 저장 (Google Drive 배포본, 조장 5/12 카톡)
- [ ] `python scripts/setup_modal_token.py` 1회 실행 (dhwang0803 워크스페이스 인증)
- [ ] llm-base Modal app 사전 배포 완료 (의존 endpoint)
- [ ] `PgNodeDefinitionRepository` 머지 완료 (REQ-001/REQ-003 — 이미 development에 있음)
- [ ] Windows: `PYTHONUTF8=1` 환경 변수 (modal CLI cp949 이슈)

## 1. Modal Secret 등록 (1회 또는 토큰 갱신 시)

본 app은 단일 시크릿 `agent-skills-builder-secret` 1개를 사용한다. 다음 4개 환경 변수를 묶어서 등록:

| key | 출처 |
|-----|------|
| `MODAL_TOKEN_ID` | `.env` (Google Drive) |
| `MODAL_TOKEN_SECRET` | `.env` |
| `LLM_BASE_URL` | llm-base 배포 후 출력되는 ASGI URL (`https://<workspace>--llm-base-llmbase-fastapi.modal.run`) |
| `EMBEDDING_BASE_URL` | 보통 `LLM_BASE_URL`과 동일 (llm-base는 LLM + Embed colocation) |
| `DATABASE_URL` | PostgreSQL DSN (`postgresql+asyncpg://user:pass@host:5432/db`) |

`.env` 일괄 등록:

```bash
python scripts/sync_modal_secrets.py agent-skills-builder-secret
```

또는 Modal CLI 직접:

```bash
modal secret create agent-skills-builder-secret \
  MODAL_TOKEN_ID=... \
  MODAL_TOKEN_SECRET=... \
  LLM_BASE_URL=... \
  EMBEDDING_BASE_URL=... \
  DATABASE_URL=...
```

## 2. Modal Deploy

```bash
PYTHONUTF8=1 modal deploy services/agents/agent-skills-builder/main.py
```

출력에 ASGI endpoint URL 표시:
`https://<workspace>--agent-skills-builder-skillsbuilderagent-fastapi.modal.run`

대시보드: https://modal.com/apps/dhwang0803/main/deployed/agent-skills-builder

## 3. 호출 계약 (Orchestrator가 부르는 형태)

### 3.1 라우팅 endpoint — `POST /v1/agent/route`

Body: `common_schemas.agent_protocol.AgentProtocolRequest`

```python
from common_schemas.agent_protocol import AgentProtocolRequest

req = AgentProtocolRequest(
    session_id=session_id,
    user_id=user_id,
    state=current_agent_state,
    personal_memory=[...],  # Orchestrator가 미리 로드한 list[MemoryEntry]
    payload={
        "source_type": "sop",  # 또는 "industry_default" / "functional_domain"
        # source_type별 추가 입력:
        # "sop":              "document": DocumentBlock.model_dump(mode="json")
        # "industry_default": "industry_code": "ecommerce"
        # "functional_domain":"domain_code": "customer_support" | "it_ops" | ...
    },
    trace_id="...",
)
```

### 3.2 응답 — SSE 스트림

`text/event-stream` 응답. 각 chunk는 `data: <json>\n\n` 형태이며 JSON은 `AgentProtocolResponse`:

```python
class AgentProtocolResponse:
    frames: list[AnySSEFrame]              # 보통 frames=[single SSEFrame]
    state_delta: dict[str, Any]
    next_action: Literal["continue", "complete", "error"]
```

`next_action`:
- `"continue"`: 진행 중 (AgentNodeFrame 등)
- `"complete"`: 정상 종료 (ResultFrame)
- `"error"`: 오류 (ErrorFrame)

### 3.3 source_type 분기

| source_type | use case | payload 추가 키 |
|-------------|----------|----------------|
| `"sop"` | `BuildFromSOPUseCase` | `document` (DocumentBlock JSON) |
| `"industry_default"` | `BuildFromIndustryDefaultUseCase` | `industry_code` (활성: `ecommerce` / 비활성 5종: `manufacturing` 등) |
| `"functional_domain"` | `BuildFromFunctionalDomainUseCase` | `domain_code` (활성 5종: `customer_support` / `it_ops` / `document_data` / `hr` / `marketing`) |

지원하지 않는 `source_type`이면 `next_action="error"` + `state_delta.error="E_SOURCE_TYPE_UNSUPPORTED"` 응답.

### 3.4 Health endpoint — `GET /v1/health`

```json
{"status": "ok", "app": "agent-skills-builder"}
```

DB(`SELECT 1`) 또는 embedder 어댑터 초기화 실패 시 503 + degrade detail 반환.

## 4. 흐름 요약

```
Orchestrator (HTTPSubAgentClient)
   ↓ POST /v1/agent/route (AgentProtocolRequest)
SkillsBuilderAgent.fastapi
   ↓ source_type 분기
   ├─ BuildFromSOPUseCase(repo, embedder, llm).execute(user_id, document, personal_memory)
   ├─ BuildFromIndustryDefaultUseCase(repo, embedder).execute(user_id, industry_code)
   └─ BuildFromFunctionalDomainUseCase(repo, embedder).execute(user_id, domain_code)
   ↓ AsyncGenerator[SSEFrame]
SSE serialize: AgentProtocolResponse(frames=[frame], next_action=...)
   ↓ "data: <json>\n\n"
Orchestrator 수신 (async for response in client.send(...))
```

## 5. 운영 메모

- **세션 관리**: 요청 단위로 `PgNodeDefinitionRepository` AsyncSession 생성, 정상 종료 시 commit / 예외 시 rollback. 격리 정책으로 일부 노드 실패해도 성공 노드는 commit.
- **격리 정책**: 3 use case 모두 동일 패턴 — convert(fail-fast), embed/upsert(isolate). `ResultFrame.payload.failed_node_types`에 실패 노드 기록.
- **idempotent upsert**: 모든 use case가 `uuid5(_NS, f"<source>:<id>:<node_type>")` deterministic key 사용 — 부분 실패 후 재실행 안전.
- **cold start**: ~2-5초 (CPU only, GPU 부팅 없음). Modal worker pool 유지를 위해 `scaledown_window=300` 적용.
- **동시 요청**: `@modal.concurrent(max_inputs=8)` — 워커당 8개 요청까지 동시 처리.
- **LLM 차단 상태**: `BuildFromSOPUseCase`는 `ModalLLMAdapter` 사용. PR #49 hotfix(`modal.Cls.from_name`)로 NotFoundError 해소됨 (이미 development에 머지).

## 6. 테스트

```bash
# 격리 정책 + 산업/직무 영역 기본 동작 — 17건
.venv/Scripts/python.exe -m pytest modules/ai_agent/tests/unit/application/skills_builder/test_build_from_functional_domain_use_case.py -v

# (5/17 plan 후속) Modal app 통합 테스트
# tests/integration/test_agent_skills_builder.py — SSE 직렬화 + source_type 분기 검증
```

## 7. 알려진 의존성 / 차단 사항

| 항목 | 상태 | 비고 |
|------|------|------|
| `scripts/setup_modal_token.py` | ❌ repo 미 push | 조장 5/12 카톡 안내, 별도 push 대기 |
| dhwang0803 Modal workspace 권한 | ⏳ 박아름 권한 확인 필요 | 조장에게 요청 |
| Modal Secret `agent-skills-builder-secret` | ⏳ 미등록 | `.env` 수령 후 sync 스크립트 실행 |
| llm-base Modal app | ✅ 배포 완료 (2026-05-12, 신정혜) | `LLM_BASE_URL` 환경변수로 주입 |
| `PgNodeDefinitionRepository` | ✅ 머지 완료 | `modules/storage/repositories/pg_node_definition_repository.py` |

## 8. 관련 문서

- 스펙: `docs/specs/REQ-004-ai-agent.md` §2.3 (멀티 에이전트 구조), §2.4 (AgentProtocolRequest/Response)
- llm-base: `services/agents/llm-base/README.md` (LLM/Embed endpoint 계약)
- Sprint 3 plan: `docs/specs/plan/sprint-3.md` (5/17 박아름 plan)
