# agent-skills-builder — Modal app 배포 가이드

> **REQ-004 §2.3** — 박아름 Skills Builder sub-agent. Main Orchestrator(`orchestrator` Modal app)가 VPC 내부 HTTP로 호출하면 `BuildFromSOPUseCase` / `BuildFromIndustryDefaultUseCase` / `BuildFromFunctionalDomainUseCase` 3 use case로 분기 라우팅하고, 결과를 SSE 스트리밍한다.
>
> CPU only — LLM / Embedding은 `llm-base` Modal app endpoint를 HTTP/RPC로 호출하는 클라이언트 패턴. GPU 점유 없음.

## 사전 체크

- [ ] Modal 계정 + flowit 워크스페이스 권한 (조장에게 요청)
- [ ] `.env` 파일 프로젝트 루트에 저장 (Google Drive 배포본, 조장 5/12 카톡)
- [ ] `python scripts/setup_modal_token.py` 1회 실행 (flowit 워크스페이스 인증)
- [ ] llm-base Modal app 사전 배포 완료 (의존 endpoint)
- [ ] `PgNodeDefinitionRepository` 머지 완료 (REQ-001/REQ-003 — 이미 development에 있음)
- [ ] Windows: `PYTHONUTF8=1` 환경 변수 (modal CLI cp949 이슈)

## 1. Modal Secret 등록 (5/19 GCP Secret Manager 마이그레이션 후)

PR #80/#81(2026-05-19) 마이그레이션으로 **Modal Secret은 `cloudsql-iam-sa` 1개만 마운트**한다. 나머지 환경 변수(`LLM_BASE_URL` / `EMBEDDING_BASE_URL` / `CLOUD_SQL_INSTANCE` / `DB_IAM_USER` / `DB_NAME`)는 `boot()`에서 `services.common.gcp_secrets.load_secrets_to_env`로 GCP Secret Manager에서 런타임 pull.

| Modal Secret | 키 | 등록자 |
|--------------|----|--------|
| `cloudsql-iam-sa` | `GOOGLE_APPLICATION_CREDENTIALS_JSON` (공용 GCP SA JSON) | 조장 1회 등록 |

sub-agent 담당자가 할 일 = **GCP IAM 권한 확인 1개**:

```powershell
gcloud secrets get-iam-policy llm-base-url --project=<GCP_PROJECT_ID> `
  --format="json(bindings[].members)"
```

출력에 본인 `user:<email>` 포함되어야 함. 없으면 조장에게 IAM 추가 요청 — `infra/terraform/envs/staging/variables.tf`의 `agent_secret_accessors` 리스트 추가 + `terraform apply`.

신규 secret이 필요하면 `agent_secret_names`에 추가 + `terraform apply` + `gcloud secrets versions add` + `main.py boot()`의 `load_secrets_to_env({...})` 매핑 추가.

상세 가이드: [`docs/guides/sub_agent_modal_deploy.md`](../../../docs/guides/sub_agent_modal_deploy.md) §3.1 (image 4종) + §3.2 (boot 패턴).

## 2. Modal Deploy

```bash
PYTHONUTF8=1 modal deploy services/agents/agent-skills-builder/main.py
```

출력에 ASGI endpoint URL 표시:
`https://<workspace>--agent-skills-builder-skillsbuilderagent-fastapi.modal.run`

대시보드: https://modal.com/apps/flowit/main/deployed/agent-skills-builder

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
{"status": "ok", "app": "agent-skills-builder", "db": "iam-connected"}
```

DB(`SELECT 1`, Cloud SQL IAM 인증) 또는 embedder 어댑터 초기화 실패 시 503 + degrade detail 반환 (errors 객체에 `db` / `embedder` 키별 사유).

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

## 7. 알려진 의존성 / 차단 사항 (5/20 시점 갱신)

| 항목 | 상태 | 비고 |
|------|------|------|
| `scripts/setup_modal_token.py` | ✅ 머지 완료 | 박아름 1회 실행으로 flowit 인증 완료 |
| flowit Modal workspace 권한 | ✅ 확인 완료 | |
| Modal Secret `cloudsql-iam-sa` | ✅ 등록 완료 (조장 1회) | 5/19 PR #80/#81 마이그레이션 후 단일 secret |
| GCP `secretmanager.secretAccessor` IAM (박아름) | ✅ 부여 완료 | Terraform `agent_secret_accessors` 등재 |
| llm-base Modal app | ✅ 배포 완료 (2026-05-12, 신정혜) | `LLM_BASE_URL` GCP Secret Manager에 등록됨 |
| `PgNodeDefinitionRepository` | ✅ 머지 완료 | `modules/storage/repositories/pg_node_definition_repository.py` |
| FastAPI Body(...) 정석 패턴 | ✅ 마이그레이션 완료 (PR #93, 5/20) | route(req: AgentProtocolRequest = Body(...)) — 우회 패턴 폐기 |

## 8. 관련 문서

- 스펙: `docs/specs/REQ-004-ai-agent.md` §2.3 (멀티 에이전트 구조), §2.4 (AgentProtocolRequest/Response)
- llm-base: `services/agents/llm-base/README.md` (LLM/Embed endpoint 계약)
- Sprint 3 plan: `docs/specs/plan/sprint-3.md` (5/17 박아름 plan)
