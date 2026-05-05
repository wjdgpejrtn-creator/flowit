# Monorepo Structure — 사내 AI 자동화 스킬 마켓플레이스

> **Baseline**: v1.0 (2026-04-30)
> **최종 갱신**: 2026-05-05
> **작성자**: 황대원 (조장)
> **아키텍처**: Clean Architecture (의존성 역전 + Port/Adapter)

---

## 1. 개요

본 프로젝트는 **마이크로서비스 아키텍처 기반의 사내 AI 자동화 스킬 마켓플레이스 플랫폼**이다.
12개 REQ 문서(Baseline v1.0)를 단일 Git 저장소(모노레포)에서 관리하며, **Clean Architecture 동심원 모델**을 디렉토리 구조로 직접 반영한다.

### 1.1 왜 모노레포인가

| 항목 | 이점 |
|---|---|
| 스키마 일관성 | `packages/common-schemas`를 Python·TypeScript 모두 참조 — 타입 불일치 원천 차단 |
| 원자적 변경 | API 스키마 변경 시 서버·프론트·스키마를 하나의 PR로 처리 |
| 코드 리뷰 효율 | 서비스 간 영향도를 단일 diff로 확인 |
| CI/CD 단순화 | 변경된 경로 기반으로 선택적 빌드·배포 |

### 1.2 Clean Architecture 핵심 규칙

| 규칙 | 설명 |
|------|------|
| **의존성 방향** | 바깥 → 안쪽만 허용. Domain은 어떤 프레임워크도 모른다 |
| **의존성 역전 (DIP)** | 안쪽이 Port(인터페이스)를 정의하고, 바깥이 Adapter(구현체)를 제공한다 |
| **경계 횡단** | 계층 간 데이터 전달은 DTO 또는 도메인 엔티티로만 한다. ORM 모델이 도메인을 넘지 않는다 |
| **테스트 독립성** | Domain과 Application은 외부 시스템 없이 단위 테스트 가능 |

---

## 2. 디렉토리 구조

```
Workflow_Automation/
│
├── packages/
│   └── common-schemas/                     # REQ-012 SSOT (최내곽 원)
│       ├── python/
│       │   ├── common_schemas/
│       │   │   ├── __init__.py
│       │   │   ├── workflow.py             # WorkflowSchema, NodeInstance, Edge, Position
│       │   │   ├── node.py                 # NodeConfig
│       │   │   ├── agent.py                # AgentState, DraftSpec, IntentResult, ...
│       │   │   ├── document.py             # DocumentBlock, ContentBlock, FileMeta, ...
│       │   │   ├── security.py             # PermissionSource, PlaintextCredential
│       │   │   ├── validation.py           # ValidationErrorResponse, ...
│       │   │   ├── transport.py            # SSEFrame 계열
│       │   │   ├── handoff.py              # HandoffPayload, EvaluationResult
│       │   │   ├── enums.py                # AgentMode, ExecutionStatus, RiskLevel, ErrorCode
│       │   │   └── exceptions.py           # DomainError 계층
│       │   └── pyproject.toml
│       ├── typescript/
│       │   ├── src/generated/              # Python → TS 자동 생성
│       │   └── package.json
│       └── scripts/                        # codegen 스크립트
│
├── modules/
│   ├── auth/                               # REQ-002 Auth-Security
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── entities/                   # Session, OAuthConnection
│   │   │   ├── value_objects/              # TokenPair
│   │   │   ├── services/                   # PermissionResolver, CredentialInjection
│   │   │   └── ports/                      # SessionRepository, OAuthRepository, CipherPort (ABC)
│   │   ├── application/
│   │   │   └── use_cases/                  # Authenticate, IssueToken, RefreshToken, InjectCredential
│   │   ├── adapters/
│   │   │   ├── cipher/                     # AESGCMCipher, FernetCipher
│   │   │   └── ...                         # GoogleOAuth, JWTAdapter, Middleware
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── unit/{domain,application}/
│   │       └── integration/adapters/
│   │
│   ├── nodes-graph/                        # REQ-003 Nodes-Graph
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── entities/                   # NodeDefinition
│   │   │   ├── services/                   # GraphValidator, GraphSerializer
│   │   │   └── ports/                      # NodeDefinitionRepository (ABC)
│   │   ├── application/
│   │   │   └── use_cases/                  # ValidateGraph, SearchNodes
│   │   ├── adapters/                       # ToolToNodeWrapper
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── unit/{domain,application}/
│   │       └── integration/adapters/
│   │
│   ├── ai-agent/                           # REQ-004 AI Agent
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── entities/                   # MemoryEntry, CorrectionPattern
│   │   │   ├── value_objects/              # EvaluationResult
│   │   │   ├── services/                   # IntentAnalyzer, QAEvaluator, Drafter, OnboardingConsultant
│   │   │   └── ports/                      # AgentMemoryRepository, NodeRegistry, LLMPort (ABC)
│   │   ├── application/
│   │   │   └── use_cases/                  # ComposeWorkflow, Onboarding
│   │   ├── adapters/
│   │   │   ├── langgraph/
│   │   │   │   ├── nodes/                  # 13개 AgentNode 구현
│   │   │   │   └── ...                     # GraphBuilder, Checkpointer
│   │   │   └── llm/                        # ModalAdapter
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── unit/{domain,application}/
│   │       └── integration/adapters/
│   │
│   ├── toolset/                            # REQ-005 Toolset
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── entities/                   # BaseTool (ABC)
│   │   │   ├── services/                   # RuntimeValidator
│   │   │   └── ports/                      # ToolRegistry, SecureConnectorPort (ABC)
│   │   ├── application/
│   │   │   └── use_cases/                  # ExecuteTool, RegisterTool
│   │   ├── adapters/
│   │   │   └── tools/                      # 8개 Tool 구현 (Google Drive, Gmail, Slack, ...)
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── unit/{domain,application}/
│   │       └── integration/adapters/
│   │
│   ├── doc-parser/                         # REQ-006 Doc Parser
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── entities/                   # ParserMeta
│   │   │   ├── services/                   # ChunkingService, QualityGate
│   │   │   └── ports/                      # ParserPort (ABC)
│   │   ├── application/
│   │   │   └── use_cases/                  # ParseDocument, ExtractChunks
│   │   ├── adapters/
│   │   │   └── parsers/                    # 7개 파서 (PDF, DOCX, XLSX, CSV, PPTX, HWP, HWPX)
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── unit/{domain,application}/
│   │       └── integration/adapters/
│   │
│   └── storage/                            # REQ-008 Persistence Adapter
│       ├── __init__.py
│       ├── orm/                            # SQLAlchemy ORM 모델 (DB 테이블 1:1)
│       ├── repositories/                   # Repository ABC 구현체
│       ├── mappers/                        # ORM ↔ 도메인 엔티티 변환
│       ├── marketplace/                    # REQ-008 고유 도메인 (5-state machine)
│       │   ├── domain/                     # SkillLifecycle, ApprovalWorkflow
│       │   └── application/
│       │       └── use_cases/              # PublishSkill, SearchSkills, ApproveSkill
│       └── tests/
│           ├── conftest.py
│           ├── unit/
│           └── integration/
│
├── services/
│   ├── api-server/                         # REQ-009 Inbound Adapter (HTTP → Use Case)
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py                     # FastAPI 엔트리포인트
│   │   │   ├── routers/                    # 13개 라우터 (얇은 Inbound Adapter)
│   │   │   ├── dependencies/               # ★ DI 컨테이너 — 전체 조립 지점
│   │   │   ├── middleware/                 # 인증·CORS·로깅·에러핸들러
│   │   │   └── sse/                        # SSE 스트리밍 핸들러
│   │   ├── tests/
│   │   │   └── conftest.py
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── execution-engine/                   # REQ-007 Worker Adapter (Celery → Use Case)
│   │   ├── src/
│   │   │   ├── __init__.py
│   │   │   ├── domain/
│   │   │   │   ├── services/               # TopologicalScheduler
│   │   │   │   └── ports/                  # WorkflowRepositoryPort, NodeExecutorPort, TaskQueuePort (ABC)
│   │   │   ├── application/
│   │   │   │   └── use_cases/              # ExecuteWorkflow, DispatchNode
│   │   │   ├── adapters/                   # CeleryAdapter, SandboxExecutor, LangGraphDispatcher
│   │   │   └── dependencies/              # Celery worker DI
│   │   ├── tests/
│   │   │   ├── conftest.py
│   │   │   ├── unit/
│   │   │   └── integration/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   └── frontend/                           # REQ-010 UI Layer
│       ├── src/
│       │   ├── app/                        # Next.js 14 App Router
│       │   ├── components/
│       │   │   ├── canvas/                 # React Flow 기반 워크플로우 캔버스
│       │   │   ├── chat/                   # AI Agent 채팅 패널
│       │   │   ├── execution/              # 실행 결과 뷰어
│       │   │   └── common/                 # 공통 컴포넌트
│       │   ├── stores/                     # Zustand 상태 관리
│       │   ├── services/                   # API 클라이언트·SSE 파서
│       │   └── types/                      # TypeScript 타입 (REQ-012에서 생성)
│       ├── public/
│       ├── tests/
│       ├── Dockerfile
│       ├── package.json
│       └── tsconfig.json
│
├── database/                               # REQ-001 Infrastructure (순수 SQL)
│   ├── schemas/                            # 15개 DDL 파일
│   ├── migrations/                         # Alembic
│   ├── seeds/                              # 초기 데이터 (node_definitions 54종 등)
│   ├── scripts/                            # DB 유틸리티
│   └── tests/
│
├── infra/                                  # REQ-011 Infrastructure
│   ├── terraform/
│   │   ├── modules/                        # 재사용 가능 Terraform 모듈
│   │   │   ├── cloud-run/                  # Cloud Run 서비스 (4개)
│   │   │   ├── cloud-sql/                  # Cloud SQL PostgreSQL 16
│   │   │   ├── memorystore/                # Memorystore Redis 7
│   │   │   ├── gcs/                        # GCS 버킷 (5개)
│   │   │   ├── secret-manager/             # Secret Manager (9개 시크릿)
│   │   │   └── networking/                 # VPC·Serverless Connector
│   │   └── envs/
│   │       ├── staging/
│   │       └── production/
│   └── docker/
│       └── docker-compose.dev.yml          # 로컬 개발 환경
│
├── docs/
│   ├── context/
│   │   ├── architecture.md
│   │   ├── clean_architecture.md           # Clean Architecture 전체 설계서
│   │   ├── decisions.md
│   │   ├── MAP.md
│   │   └── adr/                            # Architecture Decision Records
│   ├── specs/
│   └── adrs/
│
├── class_diagram/                          # 14개 .drawio 파일
├── _agent_templates/                       # Claude Agent 템플릿 (9개)
├── scripts/                                # 프로젝트 레벨 스크립트
├── .github/
│   ├── CODEOWNERS
│   ├── pull_request_template.md
│   └── workflows/
│
├── CLAUDE.md
├── MONOREPO_STRUCTURE.md                   # ← 본 문서
├── pyproject.toml
└── .gitignore
```

---

## 3. Clean Architecture 동심원 ↔ 디렉토리 매핑

```
┌─────────────────────────────────────────────────────────────────────┐
│  Frameworks & Drivers (Infrastructure)                              │
│                                                                     │
│  database/                    REQ-001  SQL·Alembic·Seeds            │
│  infra/                       REQ-011  Terraform·Docker             │
│  services/frontend/           REQ-010  Next.js 14·React Flow        │
│  External APIs                         Google·Slack·Modal GPU        │
├─────────────────────────────────────────────────────────────────────┤
│  Interface Adapters                                                 │
│                                                                     │
│  services/api-server/         REQ-009  Inbound (HTTP → Use Case)   │
│  services/execution-engine/   REQ-007  Inbound (Celery → Use Case) │
│  modules/storage/             REQ-008  Outbound (Use Case → DB)    │
│  modules/*/adapters/          각 REQ   외부 SDK·프레임워크 래핑      │
├─────────────────────────────────────────────────────────────────────┤
│  Application (Use Cases)                                            │
│                                                                     │
│  modules/*/application/       REQ-002~006  유스케이스 오케스트레이션 │
│  services/execution-engine/   REQ-007      워크플로우 실행 유스케이스 │
│       src/application/                                              │
├─────────────────────────────────────────────────────────────────────┤
│  Domain (Entities)                                                  │
│                                                                     │
│  packages/common-schemas/     REQ-012  공유 Entity·VO·Enum (SSOT)  │
│  modules/*/domain/            각 REQ   모듈 전용 도메인 로직         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. REQ ↔ 디렉토리 ↔ 담당자 매핑

| REQ | 디렉토리 | 담당자 | 우선순위 |
|---|---|---|---|
| REQ-001 | `database/` | 황대원 | P0 |
| REQ-002 | `modules/auth/` | 박아름 | P0 |
| REQ-003 | `modules/nodes-graph/` | 박아름 | P0 |
| REQ-004 | `modules/ai-agent/` | 신정혜 | P0 |
| REQ-005 | `modules/toolset/` | 햄햄 | P0 |
| REQ-006 | `modules/doc-parser/` | 김진형 | P0 |
| REQ-007 | `services/execution-engine/` | TBD | P0 |
| REQ-008 | `modules/storage/` | 황대원 | P0 |
| REQ-009 | `services/api-server/` | 황대원 | P0 |
| REQ-010 | `services/frontend/` | 황동환 | P0 |
| REQ-011 | `infra/` | 황대원 | P0 |
| REQ-012 | `packages/common-schemas/` | 황대원 | P0 |

---

## 5. 브랜치 전략

### 5.1 브랜치 종류

| 브랜치 | 용도 | 보호 규칙 |
|---|---|---|
| `main` | 안정 브랜치 | PR only, 2 approvals, CI 통과 필수 |
| `development` | 통합 브랜치 — 모든 feature PR의 base | PR only, CI 통과 필수 |
| `feature/req-XXX-*` | REQ 단위 기능 개발 | `development` 에서 분기 → `development` 으로 머지 |
| `fix/XXX-*` | 버그 수정 | `development` 에서 분기 |
| `release` | 프로덕션 배포 트리거 | `development` → `release` 머지 시 자동 배포 |

### 5.2 흐름

```
feature/req-002-auth ──┐
feature/req-004-agent ─┤
feature/req-008-storage┤──→ development ──→ release ──→ production
feature/req-010-frontend┘        │
                                 ↓
                               main (안정 병합)
```

### 5.3 브랜치 네이밍 규칙

```
feature/req-{번호}-{설명}     예: feature/req-002-google-sso
fix/req-{번호}-{설명}         예: fix/req-009-sse-timeout
hotfix/{설명}                 예: hotfix/credential-leak-patch
chore/{설명}                  예: chore/update-dependencies
```

### 5.4 feature 브랜치 생성 예시

```bash
# development에서 분기
git checkout development
git pull origin development
git checkout -b feature/req-002-auth

# 작업 후 PR 생성
git push -u origin feature/req-002-auth
gh pr create --base development --title "feat(auth): Google SSO + JWT 구현"
```

---

## 6. 의존성 그래프 — Clean Architecture 기반

### 6.1 의존성 방향

```
                    ┌──────────────────────┐
                    │ packages/            │
                    │   common-schemas/    │  ← 최내곽: 아무것도 import하지 않음
                    │   (REQ-012 SSOT)     │     (Pydantic v2만 예외 허용)
                    └──────────┬───────────┘
                               │ import
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
    modules/auth/      modules/ai-agent/   modules/doc-parser/
    modules/nodes-graph/  modules/toolset/
      domain/
      ├── ports/  ◄──── 안쪽이 인터페이스 정의
      ├── entities/
      └── services/
              │ import
              ▼
    modules/*/application/use_cases/
              │ import (Port 인터페이스만)
              ▼
    modules/*/adapters/          ← Port 구현체 제공
    modules/storage/             ← Repository 구현체 제공
              │ import
              ▼
    services/api-server/         ← DI로 조립, HTTP 라우팅
    services/execution-engine/   ← DI로 조립, Celery 디스패치
              │ import
              ▼
    database/ (SQL)
    infra/ (Terraform)
    External APIs
```

### 6.2 Port ↔ Adapter 매핑 (전체)

| Port (ABC) 위치 | Port 이름 | Adapter (구현체) 위치 |
|-----------------|----------|---------------------|
| `auth/domain/ports/` | `SessionRepository` | `storage/repositories/` |
| `auth/domain/ports/` | `OAuthConnectionRepository` | `storage/repositories/` |
| `auth/domain/ports/` | `CipherPort` | `auth/adapters/cipher/` |
| `nodes-graph/domain/ports/` | `NodeDefinitionRepository` | `storage/repositories/` |
| `ai-agent/domain/ports/` | `AgentMemoryRepository` | `storage/repositories/` |
| `ai-agent/domain/ports/` | `NodeRegistry` | `ai-agent/adapters/` |
| `ai-agent/domain/ports/` | `LLMPort` | `ai-agent/adapters/llm/` |
| `toolset/domain/ports/` | `ToolRegistry` | `toolset/adapters/` |
| `toolset/domain/ports/` | `SecureConnectorPort` | `toolset/adapters/` |
| `doc-parser/domain/ports/` | `ParserPort` | `doc-parser/adapters/parsers/` |
| `execution-engine/domain/ports/` | `WorkflowRepositoryPort` | `storage/repositories/` |
| `execution-engine/domain/ports/` | `NodeExecutorPort` | `execution-engine/adapters/` |
| `execution-engine/domain/ports/` | `TaskQueuePort` | `execution-engine/adapters/` |

### 6.3 import 규칙

| 방향 | 허용 여부 | 설명 |
|---|---|---|
| `services/*` → `modules/*` | **허용** | 서비스가 도메인 모듈을 import |
| `services/*` → `packages/*` | **허용** | 서비스가 공유 스키마를 import |
| `modules/*` → `packages/*` | **허용** | 모듈이 공유 스키마를 import |
| `modules/*` → `modules/*` | **조건부** | Port 인터페이스를 통해서만 |
| `modules/*` → `services/*` | **금지** | 순환 의존성 방지 |
| `packages/*` → `modules/*` | **금지** | 공유 패키지는 독립적 |
| `database/` → `*` | **금지** | 스키마는 순수 SQL, 코드 의존 없음 |

### 6.4 금지 의존성 (위반 시 CI 실패)

| 금지 방향 | 이유 |
|-----------|------|
| `modules/*/domain/` → SQLAlchemy, FastAPI, Celery | 도메인이 프레임워크에 의존하면 안 됨 |
| `modules/*/domain/` → `modules/*/adapters/` | 안쪽이 바깥을 모른다 |
| `modules/*/application/` → 구현체 직접 import | Port 인터페이스로만 참조 |
| `packages/common-schemas/` → `modules/*` | Foundation은 독립적 |
| `modules/*` → `services/*` | 순환 의존 방지 |

---

## 7. 모듈 내부 표준 구조

모든 도메인 모듈(`modules/*`)은 아래 3계층 구조를 따른다.

```
modules/{module_name}/
├── __init__.py
├── domain/                         # ① 최내곽 — 순수 비즈니스 로직
│   ├── entities/                   # 모듈 전용 도메인 엔티티
│   ├── value_objects/              # 모듈 전용 VO (해당 시)
│   ├── services/                   # 도메인 서비스 (순수 비즈니스 규칙)
│   └── ports/                      # 인터페이스 정의 (ABC)
├── application/                    # ② 유스케이스 — 도메인 조합 로직
│   └── use_cases/                  # 각 유스케이스 = 1 클래스, execute() 메서드
├── adapters/                       # ③ 어댑터 — 외부 시스템 연동
│   └── ...                         # SDK 래핑, 프레임워크 통합
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── domain/                 # 도메인 순수 테스트 (mock 불필요)
    │   └── application/            # 유스케이스 테스트 (Port mock)
    └── integration/
        └── adapters/               # 어댑터 통합 테스트
```

### 7.1 계층 간 의존성 규칙 (모듈 내부)

```
domain/
  ├── entities/     ← common-schemas import만 허용
  ├── value_objects/← common-schemas import만 허용
  ├── services/     ← entities + value_objects + ports + common-schemas
  └── ports/        ← entities + value_objects + common-schemas (ABC만 정의)

application/
  └── use_cases/    ← domain/* + common-schemas (ports를 통해서만 외부 접근)

adapters/
  └── ...           ← domain/ports 구현 + 외부 라이브러리 자유 사용
```

---

## 8. DI (Dependency Injection) 전략

DI 조립은 **애플리케이션 진입점**에서만 수행한다:
- `services/api-server/app/dependencies/` — FastAPI `Depends()`
- `services/execution-engine/src/dependencies/` — Celery worker 초기화

**도메인과 애플리케이션 계층은 DI 프레임워크를 모른다.**

---

## 9. 서비스별 기술 스택

| 서비스 | 언어 | 프레임워크 | 빌드 | 배포 대상 |
|---|---|---|---|---|
| `api-server` | Python 3.11 | FastAPI | pip + Docker | Cloud Run |
| `execution-engine` | Python 3.11 | Celery + LangGraph | pip + Docker | Cloud Run (Worker) |
| `frontend` | TypeScript | Next.js 14 | npm + Docker | Cloud Run |
| `common-schemas` (Py) | Python 3.11 | Pydantic v2 | pip (editable) | 라이브러리 |
| `common-schemas` (TS) | TypeScript | — | 자동 생성 | 라이브러리 |
| `database` | SQL | PostgreSQL 16 + pgvector | Alembic | Cloud SQL |
| `infra` | HCL | Terraform | terraform plan/apply | GCP |

---

## 10. GCP 인프라 매핑

| GCP 서비스 | 용도 | 관련 디렉토리 |
|---|---|---|
| Cloud Run (4개 서비스) | API Server / Frontend / Worker / Beat | `services/*/Dockerfile` |
| Cloud SQL (PostgreSQL 16) | 마스터 데이터 (37 테이블) | `database/schemas/` |
| Memorystore (Redis 7) | 세션 캐시 + Celery 브로커 | `services/execution-engine/` |
| Modal L4 GPU | Gemma 4 + BGE-M3 호스팅 | `modules/ai-agent/` |
| GCS (5개 버킷) | uploads / policy / execution-results / tfstate / backups | `infra/terraform/modules/gcs/` |
| Secret Manager | 9개 시크릿 (JWT/Fernet/OAuth 등) | `infra/terraform/modules/secret-manager/` |

---

## 11. 로컬 개발 환경

### 11.1 사전 요구사항

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- Terraform 1.5+ (infra 작업 시)

### 11.2 빠른 시작

```bash
# 1. 저장소 클론
git clone https://github.com/{org}/Workflow_Automation.git
cd Workflow_Automation

# 2. 환경 변수 설정
cp .env.example .env  # 값 채우기

# 3. 로컬 인프라 (PostgreSQL + Redis)
docker compose -f infra/docker/docker-compose.dev.yml up -d postgres redis

# 4. Python 환경 (api-server 예시)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e packages/common-schemas/python
pip install -e services/api-server[dev]

# 5. DB 스키마 적용
for f in database/schemas/*.sql; do psql $DATABASE_URL -f "$f"; done

# 6. API 서버 실행
uvicorn app.main:app --reload --app-dir services/api-server

# 7. 프론트엔드 (별도 터미널)
cd services/frontend && npm install && npm run dev
```

---

## 12. CI/CD 파이프라인

### 12.1 변경 감지 기반 빌드

```yaml
# .github/workflows/ci.yml 에서 paths 필터 활용
paths:
  - "services/api-server/**"    → api-server 테스트
  - "services/frontend/**"      → frontend 빌드·테스트
  - "modules/**"                → 전체 Python 테스트
  - "packages/**"               → 전체 테스트
  - "database/**"               → 스키마 검증
  - "infra/**"                  → terraform validate
```

### 12.2 배포 흐름

```
PR → development    : CI (lint + test + 보안스캔)
development → release : CI + Docker 빌드 + Cloud Run 배포 (자동)
release → main       : 안정 병합 (수동)
```

---

## 13. CODEOWNERS 매핑

```
# 전체
*                                   @dhwang0803-glitch @billionaireahreum

# REQ별 소유자
/packages/common-schemas/           @dhwang0803-glitch
/services/api-server/               @dhwang0803-glitch
/services/execution-engine/         # TBD
/services/frontend/                 # 황동환 GitHub 계정 추가 예정
/modules/auth/                      @billionaireahreum
/modules/nodes-graph/               @billionaireahreum
/modules/ai-agent/                  # 신정혜 GitHub 계정 추가 예정
/modules/toolset/                   # 햄햄 GitHub 계정 추가 예정
/modules/doc-parser/                # 김진형 GitHub 계정 추가 예정
/modules/storage/                   @dhwang0803-glitch
/database/                          @dhwang0803-glitch
/infra/                             @dhwang0803-glitch

# 위키 보호 (조장 approve 필수)
/docs/context/                      @dhwang0803-glitch
/MONOREPO_STRUCTURE.md              @dhwang0803-glitch
```

---

## 14. 주의사항

### 14.1 금지 사항
- `modules/*/domain/` → 프레임워크(SQLAlchemy, FastAPI, Celery, LangGraph) import 금지
- `modules/*/domain/` → `modules/*/adapters/` 방향 import 금지 (안쪽 → 바깥 금지)
- `modules/*/application/` → 구현체 직접 import 금지 (Port 인터페이스만 참조)
- `modules/` → `services/` 방향의 import 금지 (순환 의존)
- `packages/common-schemas`에 비즈니스 로직 금지 (순수 데이터 모델만)
- `database/schemas/`에 Python 코드 금지 (순수 SQL만)
- 하드코딩된 자격증명 금지 (글로벌 보안 규칙 참조)
- `main` 브랜치 직접 push 금지

### 14.2 컨벤션
- Python: ruff 포매터 + linter (line-length 120)
- TypeScript: ESLint + Next.js 규칙
- 커밋 메시지: `type(scope): description` (예: `feat(auth): Google OAuth 플로우 구현`)
- PR 제목: 70자 이하, 한국어 허용
- 테스트: 각 모듈/서비스의 `tests/` 디렉토리에 위치
- 모듈 내부 구조: 반드시 `domain/` → `application/` → `adapters/` 3계층 유지

---

> **본 문서는 Baseline v1.0 (2026-04-30) 기준으로 작성되었으며, Clean Architecture 전환을 반영하여 2026-05-05에 갱신되었다. 구조 변경 시 본 문서도 함께 갱신한다.**
