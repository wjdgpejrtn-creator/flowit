# Monorepo Structure — 사내 AI 자동화 스킬 마켓플레이스

> **Baseline**: v1.0 (2026-04-30)
> **최종 갱신**: 2026-05-03
> **작성자**: 황대원 (조장)

---

## 1. 개요

본 프로젝트는 **마이크로서비스 아키텍처 기반의 사내 AI 자동화 스킬 마켓플레이스 플랫폼**이다.
12개 REQ 문서(Baseline v1.0)를 단일 Git 저장소(모노레포)에서 관리하며, 4계층 아키텍처를 디렉토리 구조로 직접 반영한다.

### 1.1 왜 모노레포인가

| 항목 | 이점 |
|---|---|
| 스키마 일관성 | `packages/common-schemas`를 Python·TypeScript 모두 참조 — 타입 불일치 원천 차단 |
| 원자적 변경 | API 스키마 변경 시 서버·프론트·스키마를 하나의 PR로 처리 |
| 코드 리뷰 효율 | 서비스 간 영향도를 단일 diff로 확인 |
| CI/CD 단순화 | 변경된 경로 기반으로 선택적 빌드·배포 |

---

## 2. 디렉토리 구조

```
Workflow_Automation/
│
├── packages/                            ← 공유 패키지
│   └── common-schemas/                  REQ-012: Pydantic v2 → TypeScript SSOT
│       ├── python/
│       │   ├── common_schemas/          13개 Pydantic 모델 모듈
│       │   └── pyproject.toml
│       ├── typescript/
│       │   ├── src/generated/           자동 생성된 TS 타입
│       │   └── package.json
│       └── scripts/                     codegen 스크립트
│
├── services/                            ← 배포 가능한 서비스 (각각 Dockerfile 보유)
│   ├── api-server/                      REQ-009: FastAPI Core API
│   │   ├── app/
│   │   │   ├── main.py                  FastAPI 엔트리포인트
│   │   │   ├── routers/                 13개 라우터
│   │   │   ├── dependencies/            DI 컨테이너
│   │   │   └── middleware/              인증·CORS·로깅 미들웨어
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── execution-engine/                REQ-007: Celery Worker + Agent Dispatcher
│   │   ├── src/
│   │   │   ├── dispatcher/              워크플로우 디스패처
│   │   │   ├── nodes/                   노드 실행기
│   │   │   ├── runtime/                 런타임 검증·샌드박스
│   │   │   └── agent/                   LangGraph Agent WS
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   └── frontend/                        REQ-010: Next.js 14 + React Flow
│       ├── src/
│       │   ├── app/                     Next.js App Router
│       │   ├── components/              React 컴포넌트
│       │   ├── stores/                  Zustand 상태 관리
│       │   └── services/               API 클라이언트·SSE 파서
│       ├── public/
│       ├── tests/
│       ├── Dockerfile
│       ├── package.json
│       └── tsconfig.json
│
├── modules/                             ← 도메인 모듈 (서비스에서 import)
│   ├── auth/                            REQ-002: Google SSO + JWT + 6차원 권한
│   │   ├── __init__.py
│   │   ├── oauth.py                     Google OAuth 플로우
│   │   ├── jwt.py                       JWT 발급·검증
│   │   ├── permissions.py               Permission Source 결정
│   │   ├── middleware.py                인증 미들웨어
│   │   └── tests/
│   │
│   ├── nodes-graph/                     REQ-003: 54종 노드 카탈로그
│   │   ├── __init__.py
│   │   ├── catalog/                     노드 정의 (8개 카테고리)
│   │   ├── serializer.py               그래프 직렬화
│   │   ├── validator.py                SchemaValidation
│   │   └── tests/
│   │
│   ├── ai-agent/                        REQ-004: LangGraph 13 AgentNode + Skills Wizard
│   │   ├── __init__.py
│   │   ├── graph/                       LangGraph AgentNode 정의
│   │   ├── skills_wizard/              Onboarding Consultant
│   │   ├── memory/                      agent_memories + correction_patterns
│   │   └── tests/
│   │
│   ├── toolset/                         REQ-005: 8개 Tool + Secure Connector
│   │   ├── __init__.py
│   │   ├── tools/                       8개 Tool 구현
│   │   ├── connector/                   Secure Connector (OAuth/Credential)
│   │   ├── state_manager.py            State Manager
│   │   ├── validator.py                RuntimeValidation
│   │   └── tests/
│   │
│   ├── doc-parser/                      REQ-006: 비정형 문서 처리
│   │   ├── __init__.py
│   │   ├── parsers/                     PDF/DOCX/XLSX/CSV/PPTX/HWP/HWPX
│   │   ├── chunker.py                  문서 청킹
│   │   ├── quality_gate.py             품질 게이트
│   │   └── tests/
│   │
│   └── storage/                         REQ-008: Workflow + Skill + Marketplace
│       ├── __init__.py
│       ├── repositories/                Repository 패턴 구현
│       ├── marketplace/                 Skill 5상태 + 하이브리드 검색
│       └── tests/
│
├── database/                            ← REQ-001: PostgreSQL 16 + pgvector
│   ├── schemas/                         15개 SQL 스키마 파일
│   │   ├── 001_core.sql                 users / workflows / executions
│   │   ├── 002_credentials_agents_webhooks.sql
│   │   ├── 003_node_logs_partitioned.sql
│   │   ├── 004_approval_notifications.sql
│   │   ├── 005_skill_bootstrap.sql
│   │   ├── 006_doc_parser.sql
│   │   ├── 007_langgraph_checkpoints.sql
│   │   ├── 008_oauth_security.sql
│   │   ├── 009_node_definitions.sql     embedding vector(1024) + is_mvp
│   │   ├── 010_intent_feedback.sql
│   │   ├── 011_session_storage.sql
│   │   ├── 012_agent_memory.sql
│   │   ├── 013_marketplace.sql
│   │   ├── 014_audit_logs.sql
│   │   └── 015_node_logs_extended.sql
│   ├── migrations/                      Alembic 마이그레이션
│   ├── seeds/                           초기 데이터 (node_definitions 54종 등)
│   ├── scripts/                         DB 유틸리티 스크립트
│   └── tests/
│
├── infra/                               ← REQ-011: Infrastructure
│   ├── terraform/
│   │   ├── modules/                     재사용 가능 Terraform 모듈
│   │   │   ├── cloud-run/               Cloud Run 서비스
│   │   │   ├── cloud-sql/               Cloud SQL PostgreSQL 16
│   │   │   ├── memorystore/             Memorystore Redis 7
│   │   │   ├── gcs/                     GCS 버킷 (5개)
│   │   │   ├── secret-manager/          Secret Manager (9개 시크릿)
│   │   │   └── networking/              VPC·Serverless Connector
│   │   └── envs/
│   │       ├── staging/                 staging 환경 변수
│   │       └── production/              production 환경 변수
│   └── docker/
│       └── docker-compose.dev.yml       로컬 개발 환경
│
├── docs/                                ← 프로젝트 문서
│   ├── context/                         위키 (architecture, decisions, MAP)
│   │   ├── adr/                         Architecture Decision Records
│   │   ├── architecture.md
│   │   ├── decisions.md
│   │   └── MAP.md
│   ├── specs/                           기술 명세 (error_codes.md 등)
│   └── adrs/                            ADR 아카이브
│
├── scripts/                             ← 프로젝트 레벨 스크립트
│
├── _agent_templates/                    ← Claude Agent 템플릿 (9개)
│   ├── DEVELOPER.md
│   ├── IMPACT_ASSESSOR.md
│   ├── ORCHESTRATOR.md
│   ├── REFACTOR.md
│   ├── REPORTER.md
│   ├── REVIEW.md
│   ├── SECURITY_AUDITOR.md
│   ├── TEST_WRITER.md
│   └── TESTER.md
│
├── .github/
│   ├── CODEOWNERS                       모듈별 코드 소유자
│   ├── pull_request_template.md         PR 템플릿 (한국어)
│   └── workflows/
│       ├── ci.yml                       전체 lint + test
│       ├── deploy-prod.yml              Cloud Run 프로덕션 배포
│       └── secret-scan.yml              Gitleaks 시크릿 스캔
│
├── CLAUDE.md                            프로젝트 Claude Code 지침
├── MONOREPO_STRUCTURE.md                ← 본 문서
├── pyproject.toml                       Python 워크스페이스 루트
├── .gitignore
└── README.md
```

---

## 3. 4계층 아키텍처 ↔ 디렉토리 매핑

```
┌──────────────────────────────────────────────────────┐
│ Frontend Layer                                        │
│   services/frontend/          REQ-010                 │
├──────────────────────────────────────────────────────┤
│ Core API Layer                                        │
│   services/api-server/        REQ-009                 │
├──────────────────────────────────────────────────────┤
│ Domain Layer                                          │
│   modules/auth/               REQ-002                 │
│   modules/nodes-graph/        REQ-003                 │
│   modules/ai-agent/           REQ-004                 │
│   modules/toolset/            REQ-005                 │
│   modules/doc-parser/         REQ-006                 │
│   services/execution-engine/  REQ-007                 │
├──────────────────────────────────────────────────────┤
│ Persistence Layer                                     │
│   database/                   REQ-001                 │
│   modules/storage/            REQ-008                 │
├──────────────────────────────────────────────────────┤
│ Foundation                                            │
│   packages/common-schemas/    REQ-012                 │
│   infra/                      REQ-011                 │
└──────────────────────────────────────────────────────┘
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
| `docs` | 문서 전용 (`docs/context/` 편집) | `main` 에서 분기 |

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

## 6. 의존성 그래프

```
packages/common-schemas  ← 모든 Python 서비스·모듈이 참조
        │
        ├──→ modules/auth
        ├──→ modules/nodes-graph
        ├──→ modules/ai-agent
        ├──→ modules/toolset
        ├──→ modules/doc-parser
        ├──→ modules/storage
        │         │
        │         ├──→ services/api-server      (modules/* + common-schemas import)
        │         └──→ services/execution-engine (modules/* + common-schemas import)
        │
        └──→ services/frontend                  (typescript 타입만 참조)

database/  ← services/api-server, modules/storage가 스키마 참조
infra/     ← 독립 (Terraform 모듈, 서비스 배포 설정)
```

### 6.1 import 규칙

| 방향 | 허용 여부 | 설명 |
|---|---|---|
| `services/*` → `modules/*` | **허용** | 서비스가 도메인 모듈을 import |
| `services/*` → `packages/*` | **허용** | 서비스가 공유 스키마를 import |
| `modules/*` → `packages/*` | **허용** | 모듈이 공유 스키마를 import |
| `modules/*` → `modules/*` | **조건부** | 명시적 인터페이스를 통해서만 |
| `modules/*` → `services/*` | **금지** | 순환 의존성 방지 |
| `packages/*` → `modules/*` | **금지** | 공유 패키지는 독립적 |
| `database/` → `*` | **금지** | 스키마는 순수 SQL, 코드 의존 없음 |

---

## 7. 서비스별 기술 스택

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

## 8. GCP 인프라 매핑

| GCP 서비스 | 용도 | 관련 디렉토리 |
|---|---|---|
| Cloud Run (4개 서비스) | API Server / Frontend / Worker / Beat | `services/*/Dockerfile` |
| Cloud SQL (PostgreSQL 16) | 마스터 데이터 (37 테이블) | `database/schemas/` |
| Memorystore (Redis 7) | 세션 캐시 + Celery 브로커 | `services/execution-engine/` |
| Modal L4 GPU | Gemma 4 + BGE-M3 호스팅 | `modules/ai-agent/` |
| GCS (5개 버킷) | uploads / policy / execution-results / tfstate / backups | `infra/terraform/modules/gcs/` |
| Secret Manager | 9개 시크릿 (JWT/Fernet/OAuth 등) | `infra/terraform/modules/secret-manager/` |

---

## 9. 로컬 개발 환경

### 9.1 사전 요구사항

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- Terraform 1.5+ (infra 작업 시)

### 9.2 빠른 시작

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

## 10. CI/CD 파이프라인

### 10.1 변경 감지 기반 빌드

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

### 10.2 배포 흐름

```
PR → development    : CI (lint + test + 보안스캔)
development → release : CI + Docker 빌드 + Cloud Run 배포 (자동)
release → main       : 안정 병합 (수동)
```

---

## 11. CODEOWNERS 매핑

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
```

---

## 12. 주의사항

### 12.1 금지 사항
- `modules/` → `services/` 방향의 import 금지 (순환 의존)
- `packages/common-schemas`에 비즈니스 로직 금지 (순수 데이터 모델만)
- `database/schemas/`에 Python 코드 금지 (순수 SQL만)
- 하드코딩된 자격증명 금지 (글로벌 보안 규칙 참조)
- `main` 브랜치 직접 push 금지

### 12.2 컨벤션
- Python: ruff 포매터 + linter (line-length 120)
- TypeScript: ESLint + Next.js 규칙
- 커밋 메시지: `type(scope): description` (예: `feat(auth): Google OAuth 플로우 구현`)
- PR 제목: 70자 이하, 한국어 허용
- 테스트: 각 모듈/서비스의 `tests/` 디렉토리에 위치

---

> **본 문서는 Baseline v1.0 (2026-04-30) 기준으로 작성되었으며, 구조 변경 시 본 문서도 함께 갱신한다.**
