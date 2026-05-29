# CI/CD 자동화 4종 작업 계획서

**작성일**: 2026-05-28 (2026-05-29 옵션 C/E 갱신)
**작성자**: 황대원 (조장)
**담당자**: 박아름 (PR #217)
**마감**: 2026-05-31 데모 직전 (D-3)
**진행 방식**: 본 문서를 담당자가 자신의 Claude Code에 그대로 입력 → 워크플로우 신설 → 단일 PR로 development에 머지

## 목차

1. [배경](#1-배경) — 현재 워크플로우 상태 + 덱 vs 실제 갭
2. [사전 결정 사항](#2-사전-결정-사항-이미-합의됨) — pytest scope / 배포 트리거 / WIF 경로 / 황대원 확정
3. [작업 항목](#3-작업-항목) — 4 workflow yml 골격 (3.1 ruff ⏸ / 3.2 pytest ⏸ / 3.3 deploy.yml ✅ / 3.4 modal-deploy.yml ✅ / 3.5 deploy-prod.yml 삭제 ✅)
4. [사전 셋업](#4-사전-셋업-wif--secrets--branch-protection) — **WIF 신규 6단계** + Secrets 6종 등록 + Branch Protection + Repository Actions
5. [검증 방법](#5-검증-방법) — 로컬 / PR open / development 머지 후 / release FF 머지 후 4단계
6. [머지 순서](#6-머지-순서) — 사전 → PR open → 머지 → release FF → branch protection
7. [메모리/정책 참조](#7-메모리--정책-참조-담당자가-알아야-할-컨텍스트) — secret latency / SA 분리 / testcontainers / Modal 토큰 패턴
8. [진행 체크리스트](#8-진행-체크리스트-담당자용) — 담당자용 단계별 체크박스
9. [위험 / 미해결](#9-위험--미해결) — ruff format diff / WIF 함정 / Cloud Run revert 등
10. [Deferred (후속)](#10-deferred-본-pr-scope-밖--후속-작업) — prod 인프라 / ruff format 통일 / pre-commit / Slack 알림 등
11. [문의 / 의사결정](#11-문의--의사결정-권한)

---

## 1. 배경

발표 덱 PART 04에 명시된 "PR Merge 3중 게이트(Ruff·TS·pytest 자동 차단) + Cloud Run staging 자동 배포 + Modal deploy 자동화" 항목이 **실제 GitHub Actions에는 미구현**.

### 1.1 현재 `.github/workflows/` 상태 (검증 완료)

| 파일 | 역할 |
|---|---|
| `codegen-drift.yml` | pydantic2ts TypeScript drift 검사 |
| `deploy-prod.yml` | `release` 브랜치 → prod Cloud Run 자동 배포 |
| `secret-scan.yml` | gitleaks 자격증명 스캔 |

추가 검증:
- `.pre-commit-config.yaml` / husky / GitLab CI / 로컬 ci.sh **모두 없음**
- `deploy-prod.yml`에 `ruff`/`pytest`/`lint` 호출 0건
- `services/frontend/package.json scripts`에 `"test": "jest"` + `"lint": "next lint"` **둘 다 있음** (jest config는 `services/frontend/jest.config.js` + `jest.setup.ts` 존재 — `npm test` 즉시 동작)
- 루트 `pyproject.toml`에 `[tool.ruff]` + `[tool.pytest.ini_options]` config는 있지만 **CI에서 호출 안 함**
- `deploy-prod.yml`의 `docker build -f API_Server/Dockerfile`은 **stale 경로** (대문자 `API_Server/` 디렉토리 존재 안 함, 실제는 `services/api_server/Dockerfile`). 본 PR 범위 밖이지만 prod 배포는 현재 깨져있을 가능성. 별도 hotfix 필요 — 황대원에게 알릴 것
- 각 service는 `Dockerfile` + `cloudbuild.yaml` **세트로 보유**: `services/api_server/`, `services/execution_engine/`, `services/frontend/` 모두 `cloudbuild.yaml`이 build context = **repo root** + `--config=` 인자로 호출되는 패턴
- `services/agents/<name>/` 5종 중 `llm-base`만 Dockerfile 보유 (CUDA 12.8 / Ubuntu 24.04). 나머지 4종은 Modal Image API(`modal.Image.debian_slim()`)로 image 정의 — 별도 Dockerfile 없음

### 1.2 덱 vs 실제 갭

> **⚠️ 2026-05-29 갱신** — 본 v1 골격은 4 workflow 신설 가정으로 작성됐으나 **실제 PR #217은 옵션 C/E 채택으로 deploy.yml + modal-deploy.yml 2종만 본 PR scope**. ruff/pytest는 별도 트랙으로 분리. 자세한 trade-off는 [ci-cd-handoff-qa-2026-05-29.md](./ci-cd-handoff-qa-2026-05-29.md) §"PR #217 진행 중 추가 정정" + 박아름 APPROVE 리뷰 코멘트.

| 덱 주장 | 실제 | 본 PR로 해소 |
|---|---|---|
| Ruff 자동 차단 | 없음 | ⏸ **옵션 C 별도 트랙** — ruff 0.15 도입 시 365 errors (대부분 UP/I001 신규 룰). 옵션 C로 본 PR 제외, D+1 박아름 별도 PR. 본 §3.1 골격은 향후 참조용 |
| pytest 자동 차단 | 없음 | ⏸ **옵션 E 별도 트랙** — monorepo root pytest 호출 시 15 errors (execution_engine src-layout / ai_agent langgraph dep 누락 — 박아름 영역 밖). 옵션 E로 본 PR 제외, 영역 owner(황대원/신정혜) fix 머지 후 박아름이 별도 PR 재투입. 본 §3.2 골격은 향후 참조용 |
| TS drift 자동 차단 | `codegen-drift.yml` 있음 | (그대로 유지) |
| Cloud Run staging 자동 배포 | prod만 있음 | ✅ staging 배포 워크플로우 신설 (`deploy.yml`) |
| Modal deploy 자동화 | 없음 | ✅ Modal deploy 자동화 신설 (`modal-deploy.yml`) |

---

## 2. 사전 결정 사항 (이미 합의됨)

| 항목 | 결정 |
|---|---|
| pytest scope | **PG 16 service container + integration 포함 + frontend jest까지** 단일 워크플로우에서 |
| 배포 환경 | **staging 단일** — prod Cloud Run service 0건 확인(`gcloud run services list ... --filter="metadata.name~prod"` Listed 0 items). 본 프로젝트는 7/1 destroy 예정이라 prod 신설 안 함 |
| 배포 트리거 | **`push: release` (FF-only)** — `dev push` 자동 배포 폐기로 in-flight Celery task 중단 위험 해소. release 머지 = 명시적 배포 결정 시점 + 데모 시연 도중 우발적 배포 차단 |
| 배포 워크플로우 구조 | **단일 `.github/workflows/deploy.yml` 1개**. 기존 `deploy-prod.yml`은 본 PR로 **삭제** (다른 프로젝트 코드 — 본 repo에 잘못 commit됨, release 트리거 충돌 자동 해소) |
| 배포 시퀀스 | **build → staging deploy** 1단계 (prod 없음) |
| 배포 수동 승인 | **불필요** (release FF 머지 자체가 명시적 결정) |
| Modal scope | **5종 모두 release 트리거 + sub-agent matrix + paths 필터** (agent-composer / agent-orchestrator / agent-skills-builder / agent-personalization / llm-base). Modal workspace는 단일(`dhwang0803`)이라 env 구분 없음 |
| PR 구조 | **단일 PR 4 workflow** (ruff + pytest + deploy + modal-deploy) + `deploy-prod.yml` 삭제 |
| GCP project 구조 | **staging = prod 같은 project (`<GCP_PROJECT_ID>`)**, env만 분리 |
| WIF 경로 | **신규 셋업** — `<GCP_PROJECT_ID>`에 WIF pool 0개 확인(`gcloud iam workload-identity-pools list` Listed 0 items) + GitHub repo Secrets/Variables 0개 확인(`gh api .../actions/secrets/variables` total_count:0). 기존 `deploy-prod.yml`은 한 번도 실행된 적 없는 stale 코드라 WIF가 셋업된 적 없음. **WIF pool/provider/SA + GitHub Secrets 6종 전부 신규 생성** (§4.1 절차) |
| Modal 토큰 | **담당자 보유분 사용**, 황대원 발급 불필요 |
| GitHub Settings 등록 | **담당자가 직접** (황대원 권한 없음) |
| 빌드 도구 | **Cloud Build via `cloudbuild.yaml`** — 각 service에 이미 존재. `gcloud builds submit --config=services/<svc>/cloudbuild.yaml --substitutions=_TAG=$GITHUB_SHA .` 패턴 (build context = repo root). docker build + push 직접 호출 불가 (Dockerfile COPY가 repo root 기준) |
| Cloud Run 갱신 명령 | **`gcloud run services update --image=...`** (deploy 아님). deploy-prod.yml은 `gcloud run deploy`를 쓰지만 staging Terraform 모듈이 `lifecycle.ignore_changes = [image]`를 **갖고 있지 않음** — `update`로 image만 교체하고 spec은 terraform 관리 유지가 안전. 황대원 확인 필요 (아래 §2.1 참조) |
| AR repo (staging) | **`workflow-staging`** (terraform `repository_id = "workflow-${var.environment}"`). prod은 별도 `auto-workflow`. 이미지 경로: `asia-northeast3-docker.pkg.dev/<GCP_PROJECT_ID>/<AR_REPO>/<image>:<tag>` |
| DB schema 적용 | **`python -m database.scripts.migrate`** (MigrationRunner, schema_migrations 추적). `psql -f` 단순 적용 불가 — 22개 파일 + tracking 메타데이터 필요 |
| pytest 통합 테스트 PG 의존도 | **대부분 unit + in-memory** (storage/api_server/auth/modules conftest는 mock). PG 실제 연결 필요한 곳은 **`database/tests`만** — testcontainers fallback 또는 `DATABASE_URL` env 둘 다 지원. service container 띄우면 통과 |
| jest scope | **이미 동작 가능** — `services/frontend/package.json scripts.test` = `"jest"` + `jest.config.js` + `jest.setup.ts` 존재. `tests/` 디렉토리에 테스트 파일 있음. 추가 작업 0 |

### 2.1 황대원 확정 완료 (PR open 전 추가 협의 불필요)

1. **`gcloud run services update --image=`** 사용 결정 — terraform spec 보존. `gcloud run deploy`(spec 덮어쓰기) 사용 안 함
2. **tfvars 동기화 stale 무시** — 7/1 destroy 예정이라 데모까지 잠시 둠. CI가 tfvars 자동 갱신하지 않음
3. **in-flight Celery task 중단 위험** — **release 트리거 채택으로 해소**. dev push 자동 배포 자체를 폐기했으므로 데모 도중 worker가 갑자기 재배포되는 시나리오 자체 없음
4. **branch protection** — main/development/release에 ruff + pytest required status check 등록 권장. 담당자가 GitHub Settings에서 직접 등록 (§6 §8 절차)
5. **`deploy-prod.yml` 처리** — 본 PR에서 **삭제**. 다른 프로젝트(`auto-workflow` AR repo + `auto-workflow-api-prod` service)를 가리키는 코드로, 본 repo에 잘못 commit된 것. 본 프로젝트(<GCP_PROJECT_ID>)에는 prod Cloud Run 0건이라 무관

---

## 3. 작업 항목

> **⚠️ 2026-05-29 PR #217 갱신** — §3.1 Ruff / §3.2 pytest 는 **옵션 C/E로 본 PR scope 제외**, 향후 별도 PR 재투입용 골격 보존. 본 PR(#217) 실 구현 대상은 §3.3 deploy.yml + §3.4 modal-deploy.yml + §3.5 deploy-prod.yml 삭제 3건만. 결정 사유는 [§1.2](#12-덱-vs-실제-갭) 표 + [handoff-qa-2026-05-29.md](./ci-cd-handoff-qa-2026-05-29.md) 박아름 APPROVE 코멘트.

### 3.1 Ruff CI — `.github/workflows/ruff.yml`  ⏸ (옵션 C deferred)

**Trigger**
- `pull_request`
- `push: [main, development]`

**Spec**
- 전체 monorepo 한 번에 검사 (루트 `pyproject.toml`의 `[tool.ruff]` 사용 — `line-length=120`, `select=["E","F","I","N","W","UP"]`, `target-version="py312"`)
- `ruff check .` (lint)
- `ruff format --check .` (format diff 차단)

**골격**

```yaml
name: Ruff (lint + format)

on:
  pull_request:
  push:
    branches: [main, development]

# Node 24 forcing — deploy-prod.yml과 동일 패턴 (2026-06-02 강제 전환 대비).
# Ruff job은 JS action을 setup-python(노드 런타임) + checkout만 쓰므로 안전망 차원.
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"

jobs:
  ruff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          # ruff 단일 패키지라 pip cache 효과 미미 — 생략 가능. 그래도 30초 절약
          cache: pip
      - run: pip install ruff==0.4.*  # 모듈 pyproject.toml들이 `ruff>=0.4.0` pin
      - run: ruff check .
      - run: ruff format --check .
```

**참고**
- `ruff format --check .`를 호출하면 현재 codebase가 **format diff를 갖고 있을 가능성**(아직 format 강제 안 된 모듈 다수). PR open 전 로컬에서 `ruff format .`로 1회 정리 후 별도 commit 권장. 안 되면 본 step만 `continue-on-error: true`로 임시 우회 후 후속 PR로 분리
- 위 issue가 큰 경우 본 PR에서 `ruff format --check .` 제거하고 `ruff check .`만 두기

**예상 시간**: 30~45분 (format diff 정리 시 +30분)

---

### 3.2 pytest CI — `.github/workflows/pytest.yml`  ⏸ (옵션 E deferred)

**Trigger**
- `pull_request`
- `push: development`

**구조**: 2 jobs (backend / frontend)

**Backend job — `pytest-backend`**
- Python 3.12
- **PostgreSQL 16 service container** 띄움 (pgvector extension 포함)
  - 이미지: `pgvector/pgvector:pg16` 사용
  - env: `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres`, `POSTGRES_DB=workflow_test`
  - health check + ports `5432:5432`
- **편집 가능 install 대상 — 총 12 패키지** (실측 — repo 안 모든 `pyproject.toml`이 있는 디렉토리):
  - `packages/common_schemas/python` (SSOT — 가장 먼저)
  - `database` (REQ-001 — `src.helpers.migration_runner` 등 마이그레이션 도구 import에 필수)
  - `modules/auth`, `modules/nodes_graph`, `modules/ai_agent`, `modules/toolset`, `modules/doc_parser`, `modules/storage`, `modules/skills_marketplace` (8개 모듈)
  - `services/api_server`, `services/execution_engine` (2개 service)
  - **누락 주의**: `services/common`은 pyproject 없는 단순 Python 패키지(repo root에 PYTHONPATH로 노출). `services/agents/<sub-agent>`는 Modal 전용이라 install 불필요
- DB URL env: `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/workflow_test`
- 마이그레이션 적용: **`python -m database.scripts.migrate`** (MigrationRunner 사용 — `database/schemas/000_~021_*.sql` 22개를 schema_migrations 추적과 함께 순차 적용. `psql -f` 단순 실행은 안 됨)
  - MigrationRunner는 IAM 모드와 DSN 모드를 자동 분기. `DATABASE_URL`만 있으면 DSN 경로 사용.
  - `database.scripts.migrate`는 `sys.path.insert(0, database/)` 후 `from src.helpers.migration_runner ...` import — 위 editable install로 `database` 패키지 자체가 install돼야 동작
  - `database/scripts/migrate.py`의 위치는 `database/` 내부이고 `__init__.py`가 없으므로 `python -m database.scripts.migrate`는 **repo root에서 호출**해야 모듈 path가 맞음
- pgvector extension 사전 생성: MigrationRunner가 `CREATE EXTENSION IF NOT EXISTS vector`를 호출하지만 신뢰성을 위해 `psql $DATABASE_URL -c "CREATE EXTENSION IF NOT EXISTS vector"` 1회 호출 권장
- pytest 호출: 루트 `pyproject.toml`의 `[tool.pytest.ini_options]`에 testpaths가 정의돼 있어 **`pytest` 단독으로 충분**:
  ```toml
  testpaths = [
      "services/api_server/tests",
      "services/execution_engine/tests",
      "services/common/tests",
      "modules/*/tests",
      "database/tests",
      "packages/common_schemas/python/tests",
  ]
  ```
- **테스트 환경변수**:
  - 필수: `DATABASE_URL`, `DB_NAME=workflow_test`
  - 선택: `CORS_ORIGINS=""` (api_server Settings 부팅 — conftest에서 monkeypatch로 처리 중이라 CI env에는 불필요. 하지만 safety net 차원에서 둠)
  - `REDIS_URL`, `ORCHESTRATOR_URL`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID/SECRET`, `GCS_*_BUCKET` 등 — 대부분 conftest에서 `monkeypatch.setenv`로 주입 또는 Settings의 `default=""` 처리. **CI에서 별도 export 불필요**
  - 단, 통합 테스트가 Redis나 GCS에 실제 접속하는 케이스가 발견되면 그때 추가 (현재 grep 기준 0건)
- **테스트 분류 현황 (실측)**:
  - DB 실접속 필요: `database/tests`만 (4개 파일 — `test_credential_store/test_migration_runner/test_session_repo/test_vector_search/test_models/test_schema_validity`). `database/tests/conftest.py`가 `DATABASE_URL` 환경변수 또는 `database/.env` 또는 testcontainers fallback 셋 다 지원
  - 나머지 (`services/api_server/tests`, `services/execution_engine/tests`, `modules/*/tests`): **mock + in-memory** (storage/auth conftest는 In-Memory* 클래스 정의, api_server conftest는 `monkeypatch.setenv`). DB 없어도 통과
  - testcontainers 사용: `database/tests/conftest.py` 1곳뿐 (fallback only). 새로 import하는 코드 0건 — **정책 위반 0**
- pytest 호출 옵션: 루트 conftest 없음 → 모든 conftest는 디렉토리 로컬. 충돌 위험 없음

**Frontend job — `jest-frontend`**
- Node 20
- `services/frontend/package.json`은 **이미 `"test": "jest"`** 보유 + `jest.config.js` + `jest.setup.ts` 존재. **추가 작업 0**
- `tests/` 디렉토리 안에 테스트 파일 있음. `npm test`는 Next.js의 `next/jest` 래퍼를 통해 jest 자동 설정 (next.config.mjs 인식, swc 트랜스파일)
- jest interactive mode 방지: `npm test -- --watch=false --passWithNoTests`
- `--passWithNoTests`는 테스트 파일이 0개여도 exit 0 보장 — 현재 테스트 커버리지가 어떤지 모르므로 safety net

**골격**

```yaml
name: Tests (pytest + jest)

on:
  pull_request:
  push:
    branches: [development]

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"

jobs:
  pytest-backend:
    runs-on: ubuntu-latest
    timeout-minutes: 20  # PG container boot + 12 패키지 install로 5~10분 base, safety 2배

    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: workflow_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    env:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/workflow_test
      DB_NAME: workflow_test
      PYTHONUTF8: "1"  # Windows 환경은 아니지만 안전망 (스키마 .sql이 UTF-8 BOM 포함 가능)

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install workspace packages (editable)
        # 순서 중요 — common_schemas 먼저 (다른 모든 패키지가 의존). database는 마이그레이션
        # 도구 import 위해. 모듈 8종 + service 2종.
        run: |
          pip install --upgrade pip
          pip install -e packages/common_schemas/python
          pip install -e database
          pip install -e modules/auth -e modules/nodes_graph -e modules/ai_agent
          pip install -e modules/toolset -e modules/doc_parser -e modules/storage -e modules/skills_marketplace
          pip install -e services/api_server -e services/execution_engine
          pip install pytest pytest-asyncio python-dotenv

      - name: Install psql client (for extension bootstrap)
        run: sudo apt-get update && sudo apt-get install -y postgresql-client

      - name: Create pgvector extension
        # MigrationRunner도 CREATE EXTENSION을 호출하지만 안전망 차원에서 먼저 확보.
        run: psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector" || \
             psql "postgresql://postgres:postgres@localhost:5432/workflow_test" -c "CREATE EXTENSION IF NOT EXISTS vector"
        # asyncpg 스킴은 psql이 모르므로 그쪽이 실패하면 plain postgresql:// 으로 재시도.

      - name: Apply DB schemas via MigrationRunner
        # database/schemas/*.sql 22개를 schema_migrations 추적과 함께 순차 적용.
        # repo root에서 호출 필수 (python -m database.scripts.migrate가 database 패키지를 module로 인식).
        run: python -m database.scripts.migrate

      - name: Run pytest
        # 루트 pyproject.toml의 [tool.pytest.ini_options].testpaths가 모든 테스트 경로 정의함.
        # CI에서는 옵션 없이 단순 `pytest` 호출하면 자동 인식.
        run: pytest -v --tb=short

  jest-frontend:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    defaults:
      run:
        working-directory: services/frontend

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: services/frontend/package-lock.json

      - run: npm ci

      # 권장 추가: lint + typecheck (Next.js / TypeScript 컴파일 에러도 차단)
      - run: npm run lint
      - run: npx tsc --noEmit

      - run: npm test -- --watch=false --passWithNoTests
```

**참고**
- `--watch=false`는 jest 28+ 인자 (이전 `--watchAll=false` 호환). 두 옵션 다 inject해도 OK
- `tsc --noEmit`은 codegen-drift.yml에서 generated TS만 검사. frontend 본체 TS는 별도로 검증해야 함 — 위 step 추가 시 frontend가 새로 생긴 generated 타입 깨먹는 케이스 자동 차단
- `npm run lint` (`next lint`)이 ESLint 룰 위반 발견 시 exit 1. 현재 codebase가 클린한지 확인 안 됨 → 본 step도 첫 실행에서 노이즈 가능 → 통과 안 되면 `npm run lint -- --no-error-on-unmatched-pattern` 로 임시 우회 후 후속 PR로 정리

**예상 시간**: 2~3h (PG container 설정 + MigrationRunner 첫 실패 디버깅 + integration 트러블슈팅 포함)

**알려진 주의사항**
- 모듈별 editable install이라 `pip install -e .` 한 번에 안 됨 — **12개 패키지 명시** (common_schemas/python + database + modules 8 + services 2)
- 통합 테스트 중 staging Cloud SQL/GCS/Modal 직접 의존 케이스는 실측 결과 **0건**. conftest는 전부 in-memory/monkeypatch 패턴
- testcontainers 정책: 신규 import 금지. **현재 사용처는 `database/tests/conftest.py` 1곳뿐** (DATABASE_URL fallback). CI는 service container로 PG 제공하므로 testcontainers 코드 경로 발동 안 함
- MigrationRunner는 `schema_migrations` 테이블이 이미 존재하면 backfill 모드로 동작. CI의 깨끗한 DB에서는 `applied=22 skipped=0 backfilled=0` 예상
- `services/common`은 pyproject 없는 단순 Python 패키지 — repo root에 PYTHONPATH 노출돼 있어 install 불필요. `services/common/tests`는 루트 pytest config의 testpaths에 명시돼 있어 자동 수집됨
- 일부 모듈 테스트가 `common_schemas` 의 최신 타입을 import — common_schemas/python을 **가장 먼저** install 안 하면 install 순서 의존성 깨질 수 있음
- pip install 시 `database` 패키지의 `dev` extra에 `testcontainers[postgres]>=4.0.0`가 정의돼 있음. base install(`pip install -e database`)은 testcontainers 미설치. CI에서는 fallback 경로 발동 안 하니 base install로 충분

---

### 3.3 Cloud Run 배포 — `.github/workflows/deploy.yml`

**Trigger**
- `push: release` (FF-only 머지로만 도달)
- `paths`: `services/api_server/**`, `services/execution_engine/**`, `services/frontend/**`, `modules/**`, `packages/common_schemas/**`

**구조**
- staging 단일 배포 (본 프로젝트는 prod 없음)
- **시퀀스: build → staging deploy** (각 service별 단순 흐름)
- **Matrix로 변경된 service만 빌드** (paths-filter로 dispatch):
  - `services/api_server/**` 또는 `modules/**` 또는 `packages/common_schemas/python/**` 변경 → `api-server` 빌드 + staging deploy
  - `services/execution_engine/**` 또는 위 공통 경로 변경 → `execution-engine-worker` 빌드 + staging deploy
  - `services/frontend/**` 또는 `packages/common_schemas/typescript/**` 변경 → `frontend` 빌드 + staging deploy
- **Cloud Run service 이름** (terraform 실측):
  - api_server: `workflow-api-staging`
  - worker: `workflow-execution-worker-staging`
  - frontend: `workflow-frontend-staging`
- AR repo: `workflow-staging`
- GCP project: `<GCP_PROJECT_ID>` (Variable `GCP_PROJECT_ID_PROD` 그대로 재사용)
- WIF SA: **신규 생성** `<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com` (§4.1 6단계 셋업 후 사용). 옵션 B 폐기 — 본 프로젝트에 기존 WIF 0개 확인됨
- 빌드 명령: **`gcloud builds submit --config=services/<svc>/cloudbuild.yaml`** (각 service에 cloudbuild.yaml 이미 존재, build context = repo root)
- Cloud Run 갱신: `gcloud run services update --image=...` (deploy 아님 — terraform이 spec 관리, image만 교체)
- **`deploy-prod.yml` 삭제** (본 PR에 포함) — 다른 프로젝트 코드(`auto-workflow` AR/`auto-workflow-api-prod` service)로 본 프로젝트와 무관. release 트리거 충돌 자동 해소

**골격 (release 트리거 + staging 단일 배포 + cloudbuild.yaml)**

분량 절약을 위해 **api-server 풀 골격**만 보여줍니다. worker / frontend는 service 이름만 바꿔 동일 패턴 반복.

```yaml
name: Deploy to Cloud Run (staging)

on:
  push:
    branches: [release]
    paths:
      - "services/api_server/**"
      - "services/execution_engine/**"
      - "services/frontend/**"
      - "modules/**"
      - "packages/common_schemas/**"

permissions:
  contents: read
  id-token: write  # WIF 필수

concurrency:
  group: deploy-${{ github.ref }}
  cancel-in-progress: false  # release 머지 폭주 시에도 in-flight deploy 보호

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      api_server: ${{ steps.filter.outputs.api_server }}
      worker: ${{ steps.filter.outputs.worker }}
      frontend: ${{ steps.filter.outputs.frontend }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            api_server:
              - 'services/api_server/**'
              - 'modules/auth/**'
              - 'modules/ai_agent/**'
              - 'modules/nodes_graph/**'
              - 'modules/doc_parser/**'
              - 'modules/toolset/**'
              - 'modules/storage/**'
              - 'modules/skills_marketplace/**'
              - 'packages/common_schemas/python/**'
            worker:
              - 'services/execution_engine/**'
              - 'modules/auth/**'
              - 'modules/nodes_graph/**'
              - 'modules/storage/**'
              - 'packages/common_schemas/python/**'
            frontend:
              - 'services/frontend/**'
              - 'packages/common_schemas/typescript/**'

  deploy-api-server:
    needs: detect-changes
    if: needs.detect-changes.outputs.api_server == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      GCP_PROJECT_ID: ${{ vars.GCP_PROJECT_ID_PROD }}  # staging도 같은 project ID 재사용
      GCP_REGION: ${{ vars.GCP_REGION }}
      AR_REPO: workflow-staging
      SERVICE: workflow-api-staging

    steps:
      - uses: actions/checkout@v4

      - name: Validate inputs (no trailing whitespace)
        run: |
          for pair in "GCP_PROJECT_ID:${GCP_PROJECT_ID}" "GCP_REGION:${GCP_REGION}"; do
            name="${pair%%:*}"; val="${pair#*:}"
            [ -z "$val" ] && { echo "::error::$name empty"; exit 1; }
            trimmed=$(printf '%s' "$val" | tr -d '[:space:]')
            [ "$val" != "$trimmed" ] && { echo "::error::$name has whitespace"; exit 1; }
          done

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_WIF_SERVICE_ACCOUNT }}

      - uses: google-github-actions/setup-gcloud@v2

      - name: Build via Cloud Build (cloudbuild.yaml — context = repo root)
        run: |
          gcloud builds submit \
            --project="$GCP_PROJECT_ID" \
            --config=services/api_server/cloudbuild.yaml \
            --substitutions=_TAG=$GITHUB_SHA \
            .

      - name: Update Cloud Run service (image only — terraform owns spec)
        run: |
          IMAGE="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/api-server:${GITHUB_SHA}"
          gcloud run services update "$SERVICE" \
            --image="$IMAGE" --region="$GCP_REGION" --project="$GCP_PROJECT_ID" --quiet

      - name: Summary
        run: |
          echo "### Deployed (staging)" >> "$GITHUB_STEP_SUMMARY"
          echo "- service: \`${SERVICE}\`" >> "$GITHUB_STEP_SUMMARY"
          echo "- image-tag: \`${GITHUB_SHA}\`" >> "$GITHUB_STEP_SUMMARY"

  # ── worker / frontend도 동일 패턴 — 담당자가 api-server를 복제 ─────────────
  # deploy-worker:
  #   SERVICE: workflow-execution-worker-staging
  #   cloudbuild.yaml: services/execution_engine/cloudbuild.yaml
  #   image name: execution-engine-worker
  # deploy-frontend:
  #   SERVICE: workflow-frontend-staging
  #   cloudbuild.yaml: services/frontend/cloudbuild.yaml
  #   image name: frontend
```

**`deploy-prod.yml` 삭제** (본 PR에 포함) — 다른 프로젝트(`auto-workflow` AR + `auto-workflow-api-prod` service) 가리키는 stale 코드. 본 프로젝트 prod 0건 검증 완료(`gcloud run services list --filter="metadata.name~prod"` Listed 0 items). release 트리거 충돌 자동 해소.

**참조 — 인프라 현재 상태** (terraform 실측)
- GCP project ID: `<GCP_PROJECT_ID>`
- 환경: **staging만 운영**. prod Cloud Run 0건(`gcloud run services list --filter="metadata.name~prod"` Listed 0 items). 7/1 destroy 예정이라 prod 신설 안 함
- staging Cloud Run service 이름 (실측):
  - api_server: `workflow-api-staging`
  - worker: `workflow-execution-worker-staging` (terraform `workflow-execution-worker-${var.environment}`)
  - frontend: `workflow-frontend-staging`
- AR repo: `workflow-staging` (terraform `workflow-${var.environment}`)
- 현재 image tag는 `terraform.tfvars`에서 수동 관리 중. 자동화 후 GITHUB_SHA tag로 덮어쓰면 다음 `terraform apply`가 tfvars 값으로 revert — **데모 직후 destroy 예정(7/1)이므로 무시 가능**. 영구 운영하려면 모듈에 `lifecycle.ignore_changes = [template[0].containers[0].image]` 추가 별도 PR 필요
- in-flight Celery task 중단 위험 **해소** — release 트리거 채택으로 dev push 자동 배포가 사라졌고, release 머지는 명시적 결정 시점이라 사전 통보 가능

**예상 시간**: 1.5~2h (staging 단일 배포 + 3 service 패턴 복제 + cloudbuild 첫 실행 디버깅)

---

### 3.4 Modal deploy 자동화 — `.github/workflows/modal-deploy.yml`

**Trigger**
- `push: release` (FF-only) — Cloud Run deploy.yml과 동일 트리거. in-flight Modal 요청 안전 + 운영 규율 단순
- `paths`: `services/agents/**`, `modules/ai_agent/**`, `modules/skills_marketplace/**`, `modules/nodes_graph/**`, `packages/common_schemas/python/**` (Modal Image가 `add_local_dir`로 모듈을 묶기 때문)
- Modal workspace는 단일(`dhwang0803`)이므로 staging/prod env 구분 없음 — sub-agent matrix만

**구조**
- Matrix로 5개 Modal app 각각 deploy. **모두 `services/agents/` 하위 — `services/llm-base/`는 존재하지 않음** (오타 정정):
  - `agent-composer` → `services/agents/agent-composer/main.py`
  - `orchestrator` → `services/agents/orchestrator/main.py` (디렉토리명 `orchestrator`, app prefix는 `agent-` 없음)
  - `agent-skills-builder` → `services/agents/agent-skills-builder/main.py`
  - `agent-personalization` → `services/agents/agent-personalization/main.py`
  - `llm-base` → `services/agents/llm-base/main.py` (Dockerfile 사용 + Modal Volume 모델 캐시 필수)
- **변경된 app만 deploy** (paths-filter로 분기)
- Modal CLI: `pip install modal`
- 인증: `MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET` repo secret
  - 현재 팀은 **공용 Modal 토큰을 .env로 공유** 중 (Team plan 회피, `setup_modal_token.py`로 `~/.modal.toml` 영속화). GitHub Actions에서도 이 토큰을 secret으로 등록해 사용 — Modal CLI는 환경변수로 인식.

**사전 Modal 측 요건 (CI로 자동화 불가 — 황대원이 1회 셋업 완료해 둠)**
- Modal workspace = `dhwang0803` (sub-agent 간 RPC lookup이 동일 workspace 안에서만 동작)
- Modal Secret 등록돼 있어야 함: `cloudsql-iam-sa` (sub-agent 5종이 모두 이 secret을 `modal.Secret.from_name("cloudsql-iam-sa")`로 mount) + 각 agent별 `agent-<name>-secret` (LLM_BASE_URL 등). CI에서 등록하지 않음 — 황대원이 `modal secret create`로 수동 등록 (대부분 완료 — `docs/guides/sub_agent_modal_deploy.md` 참조)
- `llm-base`는 첫 deploy 전 `modal run services/agents/llm-base/main.py::download_model` 1회 실행해 Modal Volume에 Gemma 4 GGUF + BGE-M3를 backfill해야 함 (~30~40분). **CI에서 이 step 자동화 금지** — 황대원이 1회 완료 (또는 미완 시 황대원 알림 필요)

**골격**

```yaml
name: Modal deploy (sub-agents)

on:
  push:
    branches: [release]
    paths:
      - "services/agents/**"
      - "modules/ai_agent/**"
      - "modules/skills_marketplace/**"
      - "modules/nodes_graph/**"
      - "packages/common_schemas/python/**"
      - "services/common/**"  # services.common.gcp_secrets — composer/orchestrator boot에서 import

concurrency:
  # Modal app 단위로 group 분리해야 동시 머지가 서로 다른 app deploy를 막지 않음.
  group: modal-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: false

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      composer: ${{ steps.filter.outputs.composer }}
      orchestrator: ${{ steps.filter.outputs.orchestrator }}
      skills_builder: ${{ steps.filter.outputs.skills_builder }}
      personalization: ${{ steps.filter.outputs.personalization }}
      llm_base: ${{ steps.filter.outputs.llm_base }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            composer:
              - 'services/agents/agent-composer/**'
              - 'modules/ai_agent/**'
              - 'modules/skills_marketplace/**'
              - 'modules/nodes_graph/**'
              - 'packages/common_schemas/python/**'
              - 'services/common/**'
            orchestrator:
              - 'services/agents/orchestrator/**'
              - 'modules/ai_agent/**'
              - 'packages/common_schemas/python/**'
              - 'services/common/**'
            skills_builder:
              - 'services/agents/agent-skills-builder/**'
              - 'modules/ai_agent/**'
              - 'modules/skills_marketplace/**'
              - 'packages/common_schemas/python/**'
              - 'services/common/**'
            personalization:
              - 'services/agents/agent-personalization/**'
              - 'modules/ai_agent/**'
              - 'packages/common_schemas/python/**'
              - 'services/common/**'
            llm_base:
              - 'services/agents/llm-base/**'

  deploy-composer:
    needs: detect-changes
    if: needs.detect-changes.outputs.composer == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 30  # composer image build + push 평균 ~5분
    env:
      MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
      MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install modal
      # Modal CLI는 PYTHONUTF8 환경에서 안정적 — Linux는 default UTF-8이라 무관하지만 safety net.
      - run: PYTHONUTF8=1 modal deploy services/agents/agent-composer/main.py

  deploy-orchestrator:
    needs: detect-changes
    if: needs.detect-changes.outputs.orchestrator == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
      MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install modal
      - run: PYTHONUTF8=1 modal deploy services/agents/orchestrator/main.py

  deploy-skills-builder:
    needs: detect-changes
    if: needs.detect-changes.outputs.skills_builder == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
      MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install modal
      - run: PYTHONUTF8=1 modal deploy services/agents/agent-skills-builder/main.py

  deploy-personalization:
    needs: detect-changes
    if: needs.detect-changes.outputs.personalization == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
      MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install modal
      - run: PYTHONUTF8=1 modal deploy services/agents/agent-personalization/main.py

  deploy-llm-base:
    needs: detect-changes
    if: needs.detect-changes.outputs.llm_base == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 45  # CUDA 12.8 image + llama.cpp binary copy → 첫 deploy 시 ~10~15분
    env:
      MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
      MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install modal
      - run: PYTHONUTF8=1 modal deploy services/agents/llm-base/main.py
```

**예상 시간**: 1.5~2h

**알려진 주의사항**
- Modal CLI는 Linux/macOS에서 안정적. GitHub Actions ubuntu-latest 사용이라 **Windows quirks는 무관**.
- Modal app 이름은 `services/agents/<app>/main.py` 안의 `app = modal.App("agent-composer")` 선언 기반 — 별도 `--name` 플래그 불필요.
- llm-base는 Gemma 4 + BGE-M3 모델 가중치를 Modal Volume에서 로드. Volume backfill은 황대원이 1회 완료해 둠. **모델 가중치 자체가 바뀌는 경우(예: Gemma 4 → 4.5)에만 `modal run ::download_model` 재실행 필요** — CI deploy는 image rebuild만 (가중치 재다운로드 X).
- composer/orchestrator는 Modal Image가 Python **3.11** (각자 `main.py`의 `modal.Image.debian_slim(python_version="3.11")`). personalization은 3.12. CI runner의 Python 버전(3.12)은 **modal CLI 실행 전용**이므로 Modal app 안의 Python 버전과 무관.
- 빌드 실패 시 Modal logs는 워크플로우 로그에 직접 stream됨 — `modal deploy` 명령어 stdout 그대로 사용.
- Modal app 이름 충돌 방지: 팀 전체가 동일 workspace `dhwang0803` 사용. CI도 동일 토큰을 사용하므로 자동으로 동일 workspace에 deploy됨. **개인 워크스페이스로 잘못 잡히면 sub-agent URL이 달라지면서 orchestrator가 sub-agent lookup 실패** — 토큰 발급원이 `dhwang0803` workspace인지 한 번 확인 (`modal token current`로 출력되는 username)
- `services/agents/<app>/main.py` 안에서 `add_local_dir` 호출이 build context를 결정. CI checkout 디렉토리가 repo root여야 하는데 `actions/checkout@v4` default가 repo root라 OK.

---

## 4. 사전 셋업 (WIF + Secrets + Branch Protection)

**전제 변경**: 본 작업 계획서 초안은 "옵션 B (기존 prod WIF SA 재사용)"를 가정했으나, 실측 결과:

- `<GCP_PROJECT_ID>` project에 **WIF pool 0개** (`gcloud iam workload-identity-pools list --location=global --project=<GCP_PROJECT_ID>` Listed 0 items)
- GitHub repo `billionaireahreum/Workflow_Automation`에 **Secrets 0개 + Variables 0개** (`gh api repos/.../actions/secrets` total_count:0)
- 기존 `deploy-prod.yml`은 다른 프로젝트(`auto-workflow`) 가리키는 stale 코드로 **한 번도 실행된 적 없음**

→ **WIF pool/provider/SA + GitHub Secrets 6종 전부 신규 생성**. 옵션 B 폐기.

### 4.1 GCP WIF 신규 셋업 (담당자 = GCP IAM admin 권한 필요)

GCP 콘솔 또는 gcloud로 6단계. 한 번만 실행하면 영구 사용.

#### 4.1.1 WIF Pool 생성
```bash
gcloud iam workload-identity-pools create "github-actions" \
  --project=<GCP_PROJECT_ID> \
  --location=global \
  --display-name="GitHub Actions"
```

#### 4.1.2 WIF Provider 생성 (GitHub OIDC)
```bash
gcloud iam workload-identity-pools providers create-oidc "github" \
  --project=<GCP_PROJECT_ID> \
  --location=global \
  --workload-identity-pool=github-actions \
  --display-name="GitHub" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository=='billionaireahreum/Workflow_Automation'" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

`attribute-condition`이 **본 repo의 actions만 이 WIF 사용 가능**하도록 제한하는 핵심 보안 장치. 누락 시 임의 GitHub repo가 우리 GCP에 접근 가능해짐.

#### 4.1.3 Deploy용 Service Account 신규 생성
```bash
gcloud iam service-accounts create github-actions-deploy \
  --project=<GCP_PROJECT_ID> \
  --display-name="GitHub Actions Deploy"
```

→ SA email: `<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com`

#### 4.1.4 SA에 5종 role grant
```bash
SA="<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com"
for role in run.admin artifactregistry.writer iam.serviceAccountUser \
            cloudbuild.builds.builder storage.objectAdmin; do
  gcloud projects add-iam-policy-binding <GCP_PROJECT_ID> \
    --member="serviceAccount:$SA" --role="roles/$role"
done
```

| Role | 용도 |
|---|---|
| `roles/run.admin` | Cloud Run service update |
| `roles/artifactregistry.writer` | 이미지 push |
| `roles/iam.serviceAccountUser` | 런타임 SA actAs (api_server/worker/frontend SA에 대해 actAs) |
| `roles/cloudbuild.builds.builder` | `gcloud builds submit` 호출 |
| `roles/storage.objectAdmin` | Cloud Build context tarball 업로드 |

#### 4.1.5 WIF가 SA를 impersonate 가능하게 허용
```bash
PROJECT_NUMBER=$(gcloud projects describe <GCP_PROJECT_ID> --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding \
  "<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com" \
  --project=<GCP_PROJECT_ID> \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-actions/attribute.repository/billionaireahreum/Workflow_Automation"
```

#### 4.1.6 셋업 검증
```bash
# Pool/Provider 존재 확인
gcloud iam workload-identity-pools providers describe github \
  --project=<GCP_PROJECT_ID> \
  --location=global \
  --workload-identity-pool=github-actions

# SA의 role 확인 (5종 다 보여야 함)
gcloud projects get-iam-policy <GCP_PROJECT_ID> \
  --flatten="bindings[].members" \
  --filter="bindings.members:<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com" \
  --format="value(bindings.role)"
```

### 4.2 GitHub Secrets / Variables 등록 (담당자 = repo admin)

GitHub Settings → Secrets and variables → Actions. **전부 신규** (재사용 없음).

| 이름 | 종류 | 값 | 출처 |
|---|---|---|---|
| `GCP_WIF_PROVIDER` | Secret | `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github-actions/providers/github` | §4.1.2 후 `gcloud iam workload-identity-pools providers describe github ... --format='value(name)'` |
| `GCP_WIF_SERVICE_ACCOUNT` | Secret | `<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com` | §4.1.3 |
| `GCP_PROJECT_ID_PROD` | Variable | `<GCP_PROJECT_ID>` | (이름이 `_PROD`지만 실제 ID는 공용 — variable rename은 후속 작업) |
| `GCP_REGION` | Variable | `asia-northeast3` | |
| `MODAL_TOKEN_ID` | Secret | (담당자 보유) | Modal 토큰 |
| `MODAL_TOKEN_SECRET` | Secret | (담당자 보유) | Modal 토큰 |

값에 공백/개행 들어가면 `gcloud` 명령어가 "invalid reference format"으로 fail (deploy-prod.yml 안의 `Validate inputs` step이 이를 잡지만 시간 낭비). 등록 시 trim 주의.

### 4.3 Modal workspace 검증 (담당자)

```bash
modal token current
```

출력되는 username이 `dhwang0803`인지 확인. 다른 워크스페이스면 sub-agent 간 RPC lookup 실패. 토큰 발급원이 잘못된 경우 황대원에게 알릴 것.

### 4.4 CODEOWNERS 자동 reviewer 할당

`.github/CODEOWNERS`가 `@billionaireahreum @dhwang0803-glitch`를 전체 코드 owner로 등록 중. 본 PR은 `.github/workflows/` 신규 파일 4개를 추가하므로 두 명에게 자동 reviewer 할당됨. 둘 중 1명 approve로 머지 가능. 황대원(`@dhwang0803-glitch`) 또는 박아름(`@billionaireahreum`)의 approve를 기다릴 것.

### 4.5 GitHub Branch Protection Rules (담당자 = repo admin 권한 필요)

GitHub Settings → Branches → Add branch protection rule. 3개 룰 필요.

#### 4.5.1 `release` 브랜치 (가장 중요 — 배포 트리거)

| 설정 | 값 | 이유 |
|---|---|---|
| Branch name pattern | `release` | |
| Require a pull request before merging | ❌ **OFF** | development → release는 **PR 없이 직접 FF push** 패턴 (§6 #5). PR 강제하면 FF 못 함 |
| Require status checks to pass before merging | ✅ ON | |
| → Required checks | `ruff`, `pytest-backend`, `jest-frontend`, `codegen-drift`, `gitleaks` | development에서 이미 통과한 commit만 FF로 오므로 의미는 약하지만 안전망 |
| → Require branches up to date | ✅ ON | |
| **Require linear history** | ✅ **ON** | **FF-only 강제** — merge commit 차단. 데모 도중 실수로 일반 머지 하는 사고 방지 |
| Restrict who can push to matching branches | ✅ ON | release push = 즉시 staging 배포. **담당자 + 황대원만** 추가 |
| Do not allow bypassing the above settings | ✅ ON | admin도 우회 못 함 (사고 방지) |

#### 4.5.2 `development` 브랜치

| 설정 | 값 |
|---|---|
| Branch name pattern | `development` |
| Require a pull request before merging | ✅ ON |
| → Require approvals | 1 |
| → Require review from Code Owners | ✅ ON (CODEOWNERS 자동 작동) |
| Require status checks to pass before merging | ✅ ON |
| → Required checks | `ruff`, `pytest-backend`, `jest-frontend`, `codegen-drift`, `gitleaks` |
| Require conversation resolution before merging | ✅ ON |

#### 4.5.3 `main` 브랜치 (보수적 보호)

development와 동일 + `Restrict who can push to matching branches` 적용 (담당자 + 황대원만). main은 릴리즈 시점에만 머지하므로 더 엄격.

#### 4.5.4 등록 시점 — 워크플로우 머지 후

**Branch protection의 "Required status checks" 드롭다운은 해당 워크플로우가 한 번이라도 GitHub에서 실행된 후에야 선택 가능.** 본 PR 머지 전에 미리 켜놓으면 등록할 check가 없어 비어있음.

순서:
1. 본 PR open → ruff/pytest workflow가 PR-trigger로 1회 실행
2. development 머지
3. release FF 머지 → deploy.yml/modal-deploy.yml 1회 실행 (이건 required로 등록 안 함, push 트리거라)
4. **그 다음** branch protection rules 등록 (§4.5.1~4.5.3)

#### 4.5.5 release 브랜치 현재 상태 (방금 검증)

- `origin/release` 브랜치 **존재** ✅
- `origin/development`가 `origin/release`보다 **21 commits ahead** + release가 development의 ancestor → 첫 FF 머지 안전 ✅
- reset/force push 불필요

### 4.6 GitHub Repository → Actions 설정

#### 4.6.1 Actions → General

| 설정 | 값 |
|---|---|
| Actions permissions | "Allow all actions and reusable workflows" 또는 verified actions만 |
| Workflow permissions | **"Read repository contents and packages permissions"** (최소) — 각 워크플로우가 필요 시 `permissions:` 블록으로 명시적 grant. deploy.yml은 `id-token: write` 필요 (yml에 이미 적힘) |
| Allow GitHub Actions to create and approve pull requests | ❌ OFF |

---

## 5. 검증 방법

### 5.1 단일 PR 머지 전 로컬 검증

```bash
# Ruff
ruff check .
ruff format --check .   # 대규모 diff 시 본 명령만 임시 skip

# pytest (PG는 로컬 docker로 띄워서)
docker run -d --name test-pg -p 5432:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=workflow_test \
  pgvector/pgvector:pg16
# pgvector extension은 MigrationRunner가 알아서 생성. 안전망 차원에서 1회 호출.
psql postgresql://postgres:postgres@localhost:5432/workflow_test -c "CREATE EXTENSION IF NOT EXISTS vector"

export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/workflow_test"
export DB_NAME=workflow_test

# 12개 패키지 editable install (한 번만)
pip install -e packages/common_schemas/python -e database \
            -e modules/auth -e modules/nodes_graph -e modules/ai_agent \
            -e modules/toolset -e modules/doc_parser -e modules/storage -e modules/skills_marketplace \
            -e services/api_server -e services/execution_engine \
            pytest pytest-asyncio python-dotenv

# 마이그레이션 + pytest
python -m database.scripts.migrate
pytest -v

docker rm -f test-pg

# jest + lint + tsc
cd services/frontend
npm ci
npm run lint
npx tsc --noEmit
npm test -- --watch=false --passWithNoTests
```

### 5.2 PR open 시 (→ development) 검증

PR open(base: development)되면 PR-trigger를 받는 워크플로우만 동작:
- ✅ `ruff.yml` (pull_request)
- ✅ `pytest.yml` (pull_request)
- ✅ `codegen-drift.yml` (pull_request — 기존)
- ✅ `secret-scan.yml` (pull_request — 기존)
- ❌ `deploy.yml` / `modal-deploy.yml` — `push: release` 트리거만 — PR 단계에서 동작 안 함 (의도)

### 5.3 development 머지 후 (배포 전 단계)

- `development` 머지 자체는 자동 배포 trigger **없음** (release 트리거 채택 결과). 단지 코드만 통합됨
- 담당자가 검증된 development를 staging/prod에 반영하고 싶을 때 → §5.4 release FF 머지

### 5.4 release FF 머지 후 검증 (배포 실 발생 시점)

- 담당자가 `git checkout release && git merge --ff-only development && git push origin release` 실행
- release push 즉시:
  - `deploy.yml` 자동 trigger → 변경된 staging service revision 갱신
  - `modal-deploy.yml` 자동 trigger → 변경된 sub-agent만 deploy
- 검증:
  - `gcloud run services list --region asia-northeast3 --project <GCP_PROJECT_ID>`로 staging service 새 revision Ready=True
  - image tag가 release commit SHA와 일치 확인: `gcloud run services describe workflow-api-staging --region asia-northeast3 --format='value(spec.template.spec.containers[0].image)'`
  - `modal app list` — sub-agent 최신 deploy 시각 확인 (`dhwang0803--agent-composer-*` 등 5종)
  - staging frontend 접속(`https://workflow-frontend-staging-*.run.app`)에서 데모 시나리오 1회 — SSO → 워크플로우 생성 → execute → SSE 응답 정상

---

## 6. 머지 순서

1. **사전 (담당자 책임)** — 약 60~90분:
   - **GCP WIF 신규 셋업 6단계** (§4.1) — pool/provider/SA 생성 + 5종 role grant + impersonate 권한 + 검증
   - **GitHub Secrets/Variables 6종 신규 등록** (§4.2) — `GCP_WIF_PROVIDER`, `GCP_WIF_SERVICE_ACCOUNT`, `GCP_PROJECT_ID_PROD`, `GCP_REGION`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`
   - Modal workspace 검증 (§4.3) — `modal token current` username = `dhwang0803`
2. PR open (base: development, 4 workflow 파일 + `deploy-prod.yml` 삭제 — `services/frontend/package.json`은 이미 `test`/`lint` 보유, 추가 작업 없음)
3. PR 안의 4개 workflow 중 PR-trigger 가능한 2종(Ruff + pytest)이 self-trigger되어 통과해야 머지
4. **development에 머지** — 이 시점엔 자동 배포 발생 안 함 (release 트리거 채택). 4 workflow yml은 코드에 들어옴
5. 담당자(또는 황대원)가 **release FF 머지** 실행:
   ```bash
   git checkout release
   git pull origin release
   git merge --ff-only origin/development
   git push origin release
   ```
6. release push 즉시 `deploy.yml` + `modal-deploy.yml` 자동 trigger → §5.4 검증
7. 데모 D-3 임팩트 확보
8. **release FF 머지 + 첫 배포 검증 후** (§5.4 통과 확인 후), **branch protection rules** 설정 — **세부 항목은 §4.5 참조**:
   - `release` 브랜치 (§4.5.1): Require linear history ON, Require PR **OFF**, Restrict who can push (담당자+황대원), required checks 5종
   - `development` 브랜치 (§4.5.2): Require PR ON, Require approvals 1, CODEOWNERS, required checks 5종
   - `main` 브랜치 (§4.5.3): development와 동일 + Restrict who can push
   - deploy.yml / modal-deploy.yml은 push 트리거이므로 required로 등록 안 함
   - **순서 주의**: 워크플로우 1회 실행 후라야 required check 드롭다운에 노출됨 (§4.5.4)

---

## 7. 메모리 / 정책 참조 (담당자가 알아야 할 컨텍스트)

본 프로젝트의 일관 정책. 워크플로우 작성 시 위반 회피.

### 7.1 Secret latency bomb 회피
- **단일 secret을 복수 서비스가 latest fetch로 공유하면 안 됨** — 한 서비스가 갱신하면 다른 서비스 cold start가 깨짐
- 본 PR에서 신규 secret(`MODAL_TOKEN_*`, `GCP_*_STAGING`)은 GitHub Actions 전용. Cloud Run 측 secret과 중복 안 됨 — OK

### 7.2 SA 분리 원칙
- api_server / worker / Modal sub-agents 각자 dedicated SA
- 본 PR의 staging deploy SA는 GitHub Actions 전용 (Cloud Run admin + AR writer). 런타임 SA와 분리

### 7.3 testcontainers 신규 import 금지
- pytest CI에서 PG는 GitHub Actions **service container** 사용 (위 골격 yml의 `services.postgres`)
- 코드 안에서 testcontainers 라이브러리 신규 import는 금지

### 7.4 GCP project ID
- staging: `<GCP_PROJECT_ID>` (확인 명령: `terraform.tfvars` 또는 `gcloud config get project`)
- prod: 별도 project (deploy-prod.yml의 `GCP_PROJECT_ID_PROD` 변수 참조)

### 7.5 modal_shared_token 패턴
- 팀이 Modal Team plan 회피 위해 공용 토큰 1개를 .env로 공유 중
- GitHub Actions에서도 동일 토큰을 secret으로 등록해 사용
- 별칭 변경 없음

---

## 8. 진행 체크리스트 (담당자용)

- [ ] **사전 (담당자 GCP + GitHub Settings 직접 작업)** — 약 60~90분:
  - [ ] **GCP WIF 신규 셋업** (§4.1) — 본 프로젝트에 WIF 0개라 전부 신규:
    - [ ] §4.1.1 WIF Pool 생성 (`github-actions`)
    - [ ] §4.1.2 WIF Provider 생성 (`github` — OIDC, attribute-condition으로 본 repo 제한)
    - [ ] §4.1.3 Deploy SA 신규 생성 (`github-actions-deploy@...`)
    - [ ] §4.1.4 SA에 5종 role grant (run.admin / artifactregistry.writer / iam.serviceAccountUser / cloudbuild.builds.builder / storage.objectAdmin)
    - [ ] §4.1.5 WIF → SA impersonate 권한 (`roles/iam.workloadIdentityUser` + principalSet)
    - [ ] §4.1.6 셋업 검증 (provider describe + SA role 5종 확인)
  - [ ] **GitHub Secrets/Variables 6종 신규 등록** (§4.2):
    - [ ] Secret: `GCP_WIF_PROVIDER`, `GCP_WIF_SERVICE_ACCOUNT`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`
    - [ ] Variable: `GCP_PROJECT_ID_PROD` (=`<GCP_PROJECT_ID>`), `GCP_REGION` (=`asia-northeast3`)
  - [ ] Modal workspace 검증 (§4.3) — `modal token current` username = `dhwang0803`
  - [ ] Actions → General workflow permissions 확인 (§4.6.1)
- [ ] `services/frontend/package.json` — `test`/`lint` script 이미 있음. **추가 작업 없음** (검증만)
- [ ] `.github/workflows/ruff.yml` 작성
- [ ] `.github/workflows/pytest.yml` 작성 (PG container + jest 두 job)
- [ ] `.github/workflows/deploy.yml` 작성 (matrix + paths filter, staging 단일 배포, cloudbuild.yaml 사용, `gcloud run services update`)
- [ ] `.github/workflows/deploy-prod.yml` **삭제** (다른 프로젝트 stale 코드)
- [ ] `.github/workflows/modal-deploy.yml` 작성 (release 트리거, matrix + paths filter, 5 app)
- [ ] 로컬 검증 4종:
  - [ ] `ruff check .` + `ruff format --check .` (format diff 시 별도 commit)
  - [ ] docker PG로 pytest (`pgvector/pgvector:pg16` + `python -m database.scripts.migrate` + `pytest`)
  - [ ] `cd services/frontend && npm ci && npm run lint && npx tsc --noEmit && npm test -- --watch=false --passWithNoTests`
  - [ ] yml lint (`actionlint` 권장 또는 yaml validator)
- [ ] PR open (base: development) → ruff + pytest CI 통과 확인 → development 머지
- [ ] development 머지는 자동 배포 trigger 안 함 (release 트리거 채택). yml만 코드에 들어옴
- [ ] **release FF 머지 실행** (`git checkout release && git merge --ff-only origin/development && git push origin release`)
- [ ] release push 후 `gh run list --workflow=deploy.yml` + `gh run list --workflow=modal-deploy.yml`로 자동 trigger 확인
- [ ] staging Cloud Run 3종 + Modal 5종 새 revision Ready 검증 (§5.4)
- [ ] PR body에 검증 결과 코멘트 + 발표 덱 PART 04 신뢰도 회복 알림
- [ ] **(첫 배포 검증 후) branch protection rules 등록** — 세부 항목 §4.5 참조:
  - [ ] `release` 브랜치 룰 (§4.5.1) — Require linear history ON, Require PR OFF, Restrict who can push, required checks 5종
  - [ ] `development` 브랜치 룰 (§4.5.2) — Require PR ON + approvals 1 + CODEOWNERS + required checks 5종
  - [ ] `main` 브랜치 룰 (§4.5.3) — development와 동일 + Restrict who can push

---

## 9. 위험 / 미해결

| 항목 | 상세 | 대응 |
|---|---|---|
| ruff format diff 폭발 | 현재 codebase가 `ruff format`를 강제 안 한 상태 — `ruff format --check .`이 대규모 diff로 첫 실행 fail 가능 | 본 PR에서 `ruff format .` 1회 정리 commit 분리 또는 본 step 임시 제거. format 통일은 D-3 임팩트 우선이라 후순위 |
| frontend lint/tsc 첫 실행 fail | `npm run lint` (Next ESLint)과 `tsc --noEmit`은 현재 클린 통과 보장 없음 | 첫 실행 fail 시 본 step만 `continue-on-error: true`로 우회 후 후속 PR에서 정리 |
| WIF 셋업 누락/오류 | 본 PR 전 6단계 셋업 필요(§4.1). pool/provider/SA/role/impersonate 중 하나라도 빠지면 deploy 401 또는 "unable to acquire impersonated credentials" | §4.1.6 검증 단계로 사전 확인. attribute-condition 누락 시 보안 사고 — repo 제한 필수 |
| Modal first deploy timeout | llm-base는 첫 deploy 시 ~10~15분. timeout-minutes: 45 설정해 둠 | Modal logs 모니터링 |
| Cloud Run 모듈에 `ignore_changes=[image]` 부재 | `gcloud run services update`로 회피하지만, 다음 `terraform apply` 시 tfvars의 stale image로 revert. 데모 D-3 동안 무관 (7/1 destroy 예정) | §2.1 #1 확정대로 update 사용 |
| terraform.tfvars stale image | CI deploy 후 tfvars의 `api_server_image = "...:phase-f-9"`가 stale. 누군가 `terraform apply` 호출하면 staging이 옛날 image로 revert | 데모 기간 동안 `terraform apply` 금지. 7/1 destroy 후 무의미 |
| worker in-flight Celery task 중단 | release FF 머지는 명시적 결정 시점이라 사전 통보 가능. 다만 release 머지 후 worker 새 revision 전환 시 grace 없이 끊김 | 데모 시연 도중 release 푸시 안 하는 운영 규율로 회피 |
| Modal sub-agent URL 변경 | CI deploy로 sub-agent를 갈아끼우면 Modal URL은 stable(deploy 단위로 동일)이라 변경 없음. 하지만 Modal workspace가 잘못 잡히면 URL prefix가 바뀌면서 orchestrator 깨짐 | CI에서 `modal token current` step으로 workspace 검증 권장 (별도 step). 본 PR에 추가 검토 |
| Secret scope 분리 | `MODAL_TOKEN_*`이 pytest/ruff workflow에 노출되면 leak 가능 — 현재 골격은 workflow별로 env에서만 참조해 step 단위 격리 | OK — pytest/ruff yml에는 modal secret 참조 0건. deploy.yml은 `GCP_WIF_*`만 참조. 서로 secret 누출 없음 |
| 빈 jest 테스트 | frontend `tests/`에 실제 테스트가 있는지 미검증. `--passWithNoTests`로 fail 회피 | 본 PR scope 밖, 검증으로 충분 |
| frontend cloudbuild의 `_API_PROXY_TARGET` hardcoded URL | staging api_server URL이 `https://<API_SERVICE_URL>`로 박혀있음 — 도메인 변경 시 별도 substitution 필요 | 데모까지는 그대로 |
| release FF 머지 빈도 | dev push 자동 배포 폐기로 demo 시연 데이터 만들 때 release 머지 자주 해야 함. 부담 가능 | release를 staging 트리거처럼 적극 사용 |

---

## 10. Deferred (본 PR scope 밖 — 후속 작업)

데모 D-3 일정 우선으로 본 PR에 포함 안 함. 머지 후 별도 PR로 처리 권장.

| 항목 | 권장 시점 | 비고 |
|---|---|---|
| prod 인프라 신설 + 분리 trigger 정식화 | 7/1 이후 영구 운영 시 | 현재 prod Cloud Run 0건. 영구 운영 진입 시 prod 모듈 추가 + staging은 development push / prod은 main 머지 또는 tag로 분리 |
| Cloud Run 모듈에 `lifecycle.ignore_changes = [image]` 추가 | D+1 이후 | 본 PR의 deploy를 안정화하려면 필수. 데모 직전엔 변경 회피 |
| ruff format 통일 | D+1 이후 | `ruff format .` 1회 적용 + 별도 PR. format strict는 본 PR로 차단되면 모든 후속 PR이 막힘 |
| frontend ESLint + tsc 클린업 | D+1 이후 | 현재 lint/tsc 통과 여부 미검증 |
| pre-commit hook | 향후 | 로컬에서 ruff/secret-scan 사전 차단. push 후 CI 실패하는 cycle 단축 |
| Slack/Discord 알림 | 향후 | 팀 컨벤션 없음. 데모 후 검토 |
| terraform.tfvars 자동 갱신 | 7/1 destroy 후 무관 | image tag 자동화 영구 인프라 운영 시 필요 |
| Modal `download_model` Volume 재backfill 자동화 | 향후 | 모델 가중치 변경 빈도 낮음. 수동 유지 OK |
| `actionlint` GitHub Action 자체 검사 | 향후 | CI/CD 워크플로우 정확성 메타 검증 |
| worker `environment: staging-worker` protection rule | 영구 운영 시 | release 머지로 worker 자동 갱신 시 in-flight task 끊김 한계가 신경 쓰이면 manual approval 게이트 추가 가능 |

---

## 11. 문의 / 의사결정 권한

- 본 문서 의사결정 책임: 황대원 (조장)
- GCP WIF 신규 셋업(§4.1) + 워크플로우 yml 구현 + GitHub Settings 등록(§4.2) + Branch Protection 등록(§4.5): `[담당자 이름]`
- Modal 토큰: 담당자 보유
- 데모 마감 일정 변경 권한: 황대원
