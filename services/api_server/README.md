# api_server

> REQ-009: FastAPI 기반 HTTP 게이트웨이, SSE 스트리밍, Composition Root
>
> 구현 명세 → [`docs/specs/REQ-009-api-server.md`](../../docs/specs/REQ-009-api-server.md)

## 설치

```bash
pip install -e services/api_server
pip install -e "services/api_server[dev]"
```

## 실행

```bash
uvicorn app.main:create_app --factory --reload --port 8000
```

## 아키텍처 역할

API 서버는 **Composition Root** — 비즈니스 로직을 직접 구현하지 않고, 모든 유스케이스를 Port 인터페이스를 통해 호출합니다. 구체 구현체는 `DependencyContainer`에서 주입합니다.

## 라우터 카탈로그

| 라우터 | 주요 엔드포인트 | 위임처 |
|--------|---------------|--------|
| `workflows` | `POST/GET/PUT/DELETE /workflows[/{id}]` | REQ-008 Storage |
| | `POST /workflows/{id}/validate` | REQ-003 GraphValidator |
| | `POST /workflows/{id}/execute` | REQ-007 Celery dispatch |
| `agents` | `POST /agents/sessions` | REQ-004 ComposeWorkflowUseCase |
| | `GET /agents/sessions/{id}/stream` | SSE 스트리밍 (AnySSEFrame) |
| | `POST /agents/sessions/{id}/messages` | REQ-004 ContinueConversationUseCase |
| `documents` | `POST /documents/upload` | REQ-008 Storage + GCS |
| | `GET /documents/{id}` | REQ-006 ParseDocumentUseCase |
| | `POST /documents/{id}/analyze` | REQ-004 문서 분석 |
| `auth` | `GET /auth/{authorize,callback,me}`, `POST /auth/{refresh,logout}` | REQ-002 Authenticate/RefreshToken UseCase — ADR-0021 HttpOnly 쿠키 인증 (callback 302 + refresh/logout 쿠키 기반) |
| `nodes` | `GET /nodes/catalog` | REQ-003 NodeDefinitionRepository (56종 — gemma_chat 포함, PR #68 5/15) |
| `skills` | `POST /skills/bootstrap`, `GET /skills` | REQ-013 후보 skills_marketplace (ADR-0012 v3 신설) |
| `marketplace` | `GET /marketplace`, `POST /marketplace/{id}/promote` | REQ-013 후보 PromoteToTeam/PromoteToCompany |
| `exec_control` | `POST /executions/{id}/cancel`, `/resume` | REQ-007 PauseResumeUseCase |
| `health` | `GET /health` | 자체 (DB + Redis + Orchestrator 연결성 점검) |

## DAG 검증 / 스케줄링 책임 분리

api_server는 DAG 위상 정렬을 직접 수행하지 않는다 (PR #67 이후 단일 소유 정책).

| 작업 | 책임 모듈 | 호출 시점 |
|------|----------|----------|
| 그래프 유효성 검증 (cycle, isolated, dup-id) | `nodes_graph.domain.services.GraphValidator` | `POST /workflows/{id}/validate` 라우터 |
| 위상 정렬 + 레벨별 실행 그룹 계산 | `execution_engine.src.domain.services.TopologicalScheduler` | Celery worker 내부 (POST /workflows/{id}/execute dispatch 후) |

## SSE 스트리밍 프레임

| 프레임 | 페이로드 | 생성 주체 |
|--------|---------|----------|
| `SessionFrame` | session_id, langgraph_thread_id | 본 모듈 |
| `AgentNodeFrame` | 현재 실행 AgentNode 명 | REQ-004 |
| `RationaleDeltaFrame` | 사고 과정 실시간 델타 | REQ-004 |
| `SlotFillQuestionFrame` | Slot Filling 재질문 | REQ-004 |
| `DraftSpecDeltaFrame` | draft_spec 증분 | REQ-004 |
| `ResultFrame` | `intent: IntentType` (clarify/draft/refine/propose/build_skill — v0.4.0 PR #72) | REQ-004 (Orchestrator 발신, 본 모듈은 패스스루) |
| `ErrorFrame` | 차단/실패 메시지 | 본 모듈 또는 REQ-004 |

> 모든 프레임은 `AnySSEFrame` discriminated union으로 `frame_type` 기반 역직렬화.
> SSE 본문은 Orchestrator Modal app(HTTP)이 발송하며, api_server는 **프록시/패스스루** 역할만 수행한다.
> Personalization `update_memory` 흐름은 orchestrator 내부 처리 — api_server는 직접 호출하지 않는다 (PR #70).

## Permission Source Key

`request.state.permission_source` — 모든 유스케이스 호출 시 전달:

| 필드 | 설명 |
|------|------|
| `user_id`, `role`, `department_id` | JWT payload (REQ-002) |
| `session_id` | chat / workflow / direct |
| `granted_scopes` | 허용 범위 (Private / Team / Public) |
| `risk_ceiling` | 시도 가능한 최대 risk_level (User: High / Admin: Restricted) |

## 의존 관계

```
Upstream (이 서비스가 의존 — Use Case 호출):
  ├── auth (REQ-002)              → AuthenticateUseCase, PermissionResolver
  ├── ai_agent (REQ-004)          → Orchestrator Modal app (HTTP 어댑터 OrchestratorClient 경유, in-process import 금지)
  ├── doc_parser (REQ-006)        → ParseDocumentUseCase, ParsingPipeline
  ├── nodes_graph (REQ-003)       → ValidateGraphUseCase, SearchNodesUseCase
  ├── toolset (REQ-005)           → ListToolsUseCase
  ├── storage (REQ-008)           → ORM/Repository/Mapper SSOT (ADR-0012 v3) — async Repository (Workflow/Session/Skill 등)
  ├── database (REQ-001)          → 순수 SQL 마이그레이션 + schema_migrations bootstrap (런타임 호출 없음, 부팅 전 적용)
  ├── skills_marketplace (REQ-013 후보) → SearchSkillsUseCase, PromoteToTeam/PromoteToCompany (ADR-0012 v3 신설 모듈)
  ├── common_schemas (REQ-012)    → 모든 DTO/응답 모델 (IntentType, AgentProtocolRequest/Response 등)
  └── execution_engine (REQ-007)  → Celery task dispatch만 (직접 import 0건 — Celery broker 경유)

Downstream (이 서비스를 소비):
  └── frontend (REQ-010)          → HTTP REST + SSE 클라이언트
```

`workflow-manager` 모듈은 도입하지 않는다 (ADR-0012 v3 영구 결정). 워크플로우 CRUD는 라우터가 `dependencies/`로 주입받은 `WorkflowRepository`(modules/storage)를 직접 호출한다.

## 환경 변수

### 공통
| 변수명 | 필수 | 설명 |
|--------|------|------|
| `API_HOST` | N | 바인딩 호스트 (기본: 0.0.0.0) |
| `API_PORT` | N | 바인딩 포트 (기본: 8000) |
| `CORS_ORIGINS` | Y | 허용 오리진 목록 (쉼표 구분) |
| `REDIS_URL` | Y | Redis (세션 캐시 + Celery broker) |
| `ORCHESTRATOR_URL` | Y | ai_agent Orchestrator Modal app HTTPS URL (in-process import 금지) |
| `ORCHESTRATOR_TIMEOUT_S` | N | Orchestrator HTTP 호출 timeout (기본: 60) |

### DB 연결 — staging/prod (Cloud SQL IAM, [[sub_agent_cloud_sql_iam]] 표준)
| 변수명 | 필수 | 설명 |
|--------|------|------|
| `CLOUD_SQL_INSTANCE` | Y | `project:region:instance` (예: `wf-auto:asia-northeast3:wf-pg`). sub-agent 표준과 동일 변수명 ([[sub_agent_cloud_sql_iam]]) |
| `DB_IAM_USER` | Y | IAM SA 이메일 (예: `api-server-sa@wf-auto.iam`). 비밀번호 없음 — 런타임 SA 토큰 |
| `DB_NAME` | Y | DB 이름 |

### DB 연결 — 로컬 dev only (DSN fallback)
| 변수명 | 필수 | 설명 |
|--------|------|------|
| `DB_HOST` / `DB_PORT` / `DB_PASSWORD` | dev only | 로컬 PostgreSQL 평문 DSN. staging/prod에서는 사용 금지 (IAM 강제) |

## 아키텍처 제약

- 비즈니스 로직 직접 구현 금지 — 항상 위임처 호출
- credential 평문은 라우터 코드에서 절대 다루지 않음
- doc_parser 자체 REST 노출 금지 — 본 모듈 경유만
- **ORM 모델 직접 직렬화 금지** (ADR-0012 v3) — Repository를 통해 도메인 엔티티(common_schemas) 수신 후 응답 모델로 변환
- **DAG 위상 정렬 직접 구현 금지** (PR #67) — `execution_engine.TopologicalScheduler` 단일 소유. api_server는 cycle 등 정적 검증만 `GraphValidator`로 수행
- **WorkflowSchema 저장 시점에 `owner_user_id` 명시 주입** (PR #66 v0.3.0) — Repository.save 호출 전 `permission_source.user_id` 채움. DB는 `workflows.user_id NOT NULL`이라 누락 시 ValueError
- **ai_agent in-process import 금지** — Orchestrator HTTP 어댑터(`adapters/orchestrator_client.py`)만 경유. SSE 본문은 패스스루

## 비기능 제약

| 항목 | 기준 |
|------|------|
| 일반 라우터 P95 | < 200ms |
| SSE 첫 프레임 도달 (TTFB) | < 1초 |
| 파일 업로드 10MB | < 5초 |
| credential 평문 노출 | 0건 |
| 관측성 | 모든 응답에 X-Request-Id 헤더 |

## 테스트

```bash
pytest services/api_server/tests/
```
