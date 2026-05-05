# Workflow Automation 팀 실무 가이드

> 이 문서는 팀원 전원이 동일한 워크플로우로 개발할 수 있도록 작성된 실무 안내서입니다.
> 아키텍처 세부 사항은 각 모듈 README와 `docs/context/`를 참조하세요.

---

## 1. 프로젝트 한 줄 요약

사내 AI 자동화 스킬 마켓플레이스. 사용자가 자연어로 업무 자동화를 요청하면, AI 에이전트가 54종 노드를 조합해 워크플로우를 생성하고 실행 엔진이 LangGraph StateGraph + TopologicalScheduler(위상 정렬)로 실행한다.

---

## 2. 팀 구성 및 담당 모듈

| 담당자 | REQ | 모듈/서비스 | README 위치 |
|--------|-----|-----------|------------|
| 황대원 (조장) | 001, 007~012 | database, execution-engine, storage, api-server, frontend, infra, common-schemas | 각 모듈 하위 `README.md` |
| 박아름 (리포 오너) | 002, 003 | auth, nodes-graph | `modules/auth/`, `modules/nodes-graph/` |
| 신정혜 | 004 | ai-agent | `modules/ai-agent/` |
| 햄햄 | 005 | toolset | `modules/toolset/` |
| 김진형 | 006 | doc-parser | `modules/doc-parser/` |

---

## 3. 저장소 구조 한눈에 보기

```
Workflow_Automation/
├── packages/common-schemas/    ← 공유 타입 (Pydantic v2, 모든 모듈의 기반)
├── modules/                    ← 도메인 모듈 (비즈니스 로직)
│   ├── auth/                   ←   인증/권한 (REQ-002)
│   ├── nodes-graph/            ←   노드 카탈로그 + 그래프 검증 (REQ-003)
│   ├── ai-agent/               ←   AI 워크플로우 생성 (REQ-004)
│   ├── toolset/                ←   외부 도구 실행 (REQ-005)
│   ├── doc-parser/             ←   문서 파싱 (REQ-006)
│   └── storage/                ←   ORM + Repository 구현체 (REQ-008)
├── services/                   ← 서비스 (조립 + 인프라)
│   ├── api-server/             ←   FastAPI 게이트웨이 (REQ-009)
│   ├── execution-engine/       ←   Celery 실행 엔진 (REQ-007)
│   └── frontend/               ←   Next.js 14 UI (REQ-010)
├── _agent_templates/           ← Claude Code 에이전트 템플릿 (9개)
├── .claude/commands/           ← Claude Code 슬래시 커맨드
├── docs/                       ← 문서
│   └── context/                ←   공용 위키 (MAP, architecture, decisions)
└── CLAUDE.md                   ← Claude Code 프로젝트 지침
```

---

## 4. 브랜치 전략

### 브랜치 종류

| 브랜치 | 용도 | 누가 merge 하는가 |
|--------|------|-----------------|
| `main` | 안정 브랜치 (CI/CD 트리거) | 리포 오너(박아름) 또는 조장(황대원) — 릴리즈 시점에만 |
| `development` | 통합 브랜치 | 팀원 누구나 (PR 리뷰 후) |
| `feature/req-xxx-*` | REQ 기능 개발 | 담당자가 development로 PR |
| `hotfix/*` | 배포 후 긴급 버그 | 필요 시 생성 |
| `docs` | `docs/context/` 편집 전용 | 별도 PR |

### 커밋 경로 — 이것만 기억하세요

```
                          ┌─ REQ 기능 구현 ─→ feature/req-xxx-* 브랜치 생성 → development PR
                          │
  코드 변경 발생 ──────────┤
                          │
                          └─ 자잘한 수정 ───→ 현재 브랜치에서 커밋 → PR (브랜치 생성 X, 리뷰 필수)
                               (문서, 설정,
                                오타, 디버깅)

  development → main : 릴리즈 타이밍에만 (조장/리포 오너 판단)
```

**핵심 원칙:**
1. 모든 변경은 PR 리뷰를 거친다
2. 개발 단계에서 자잘한 수정마다 별도 브랜치를 만들지 않는다
3. `main`에 직접 PR하지 않는다 — base는 항상 `development`

---

## 5. 일상 개발 워크플로우

### A. 새 기능 개발 (REQ 작업)

```bash
# 1) development에서 feature 브랜치 생성
git checkout development
git pull origin development
git checkout -b feature/req-004-intent-analyzer

# 2) 코드 작성 (README 먼저 읽기!)
#    → modules/ai-agent/README.md 확인

# 3) 커밋
git add modules/ai-agent/
git commit -m "feat(ai-agent): IntentAnalyzerService 구현"

# 4) 푸시 + PR
git push -u origin feature/req-004-intent-analyzer
# Claude Code에서: /PR-report 실행하면 자동으로 PR 생성
```

### B. 자잘한 수정 (문서, 설정, 오타, 디버깅)

```bash
# 1) 현재 작업 중인 브랜치에서 그대로 커밋
git add .claude/commands/PR-report.md
git commit -m "fix: PR-report 오타 수정"

# 2) 푸시 → 기존 PR에 자동 반영되거나 /PR-report로 새 PR 생성
git push
```

별도 브랜치를 만들 필요 없습니다. 단, PR 리뷰는 필수입니다.

### C. `docs/context/` 수정 (공용 위키)

위키 파일은 코드 브랜치에서 수정하지 않습니다.

```bash
git checkout docs
# 수정 후
git add docs/context/
git commit -m "docs: architecture.md 실행 모드 업데이트"
git push origin docs
# 별도 PR 생성
```

---

## 6. Claude Code 사용법

### 슬래시 커맨드

| 명령어 | 기능 |
|--------|------|
| `/PR-report` | 보안 점검 → 위키 감사 → 커밋 → 푸시 → PR 생성 (전 과정 자동화) |
| `/review` | PR 코드 리뷰 |
| `/security-review` | 현재 브랜치 보안 리뷰 |
| `/init` | CLAUDE.md 초기화 |

### 에이전트 템플릿 (`_agent_templates/`)

TDD 사이클이나 코드 리뷰에 활용할 수 있는 에이전트 템플릿 9개가 준비되어 있습니다.

| 에이전트 | 언제 쓰는가 |
|----------|-----------|
| `ORCHESTRATOR` | TDD 전체 사이클 실행 시 |
| `TEST_WRITER` | 실패 테스트부터 작성할 때 (Red) |
| `DEVELOPER` | 테스트 통과하는 최소 구현 (Green) |
| `TESTER` | 테스트 실행 + 결과 수집 |
| `REFACTOR` | 코드 품질 개선 (Refactor) |
| `REVIEW` | 방어적 코드 리뷰 (8축 점검) |
| `REPORTER` | 결과 보고서 생성 |
| `SECURITY_AUDITOR` | 자격증명/PII 노출 탐지 |
| `IMPACT_ASSESSOR` | PR 전 사후 영향 평가 |

사용 방법: Claude Code에서 해당 템플릿 파일을 참조하며 작업을 요청합니다.

```
# 예시: TDD 사이클 실행
"_agent_templates/ORCHESTRATOR.md 참고해서 modules/auth/domain/services/에 대해 TDD 사이클 실행해줘"
```

---

## 7. 코드 작성 전 체크리스트

코드를 작성하기 전에 아래를 반드시 확인하세요.

### 1단계: README 읽기

```
내가 작업할 모듈의 README.md를 읽었는가?
  → Quick Start (import 패턴)
  → 의존 관계 (허용된 의존성)
  → 환경 변수 (하드코딩 금지)
  → 에러코드 (기존 체계와 충돌 없는지)
```

### 2단계: 레이어 배치 판단

```
내가 작성하는 코드는 어느 레이어인가?

  domain/entities/     → 순수 비즈니스 엔티티 (프레임워크 import 금지)
  domain/services/     → 비즈니스 규칙 (프레임워크 import 금지)
  domain/ports/        → 인터페이스 ABC 정의
  application/         → 유스케이스 (Port ABC만 참조)
  adapters/            → 외부 시스템 연동 (프레임워크 OK)
```

### 3단계: import 가능 여부 확인

```
내가 import하려는 대상이 허용된 경로인가?

  ✅ 허용:
    from common_schemas import WorkflowSchema
    from auth.domain.services import CredentialInjectionService
    from nodes_graph.domain.ports import NodeDefinitionRepository

  ❌ 금지:
    from storage.orm import UserModel          (domain에서 ORM 참조)
    from fastapi import Depends                (domain/application에서 프레임워크)
    from ai_agent.adapters.llm import ...      (다른 모듈의 adapter 직접 참조)
```

### 4단계: 보안 점검

```
  ❌ API_KEY = "abcd1234"                     → os.getenv("API_KEY")
  ❌ host=os.getenv("DB_HOST", "10.0.0.1")    → os.getenv("DB_HOST")
  ❌ .env 파일 git 추적                        → .gitignore 확인
```

---

## 8. 모듈 내부 구조 (공통)

모든 도메인 모듈은 Clean Architecture 3계층 구조를 따릅니다.

```
modules/{module_name}/
├── domain/                   ← 최내곽: 순수 비즈니스 로직
│   ├── entities/             ←   도메인 엔티티
│   ├── value_objects/        ←   값 객체
│   ├── services/             ←   도메인 서비스
│   └── ports/                ←   인터페이스 (ABC)
├── application/              ← 중간: 유스케이스
│   └── use_cases/            ←   1 클래스 = 1 유스케이스, execute() 메서드
├── adapters/                 ← 최외곽: 외부 연동
│   └── ...
└── tests/
    ├── unit/domain/          ←   순수 테스트 (mock 불필요)
    ├── unit/application/     ←   유스케이스 테스트 (Port mock)
    └── integration/          ←   어댑터 통합 테스트
```

### 의존성 방향 (안쪽 → 바깥 참조 금지)

```
  adapters/ → application/ → domain/ → common-schemas
     ↓ OK      ↓ OK           ↓ OK
  외부 라이브러리  Port ABC만     common-schemas만
```

**Port와 Adapter가 분리되는 핵심 이유:**
- `domain/ports/`에 인터페이스(ABC)를 정의
- `storage/repositories/` 또는 자체 `adapters/`에 구현체를 배치
- `services/api-server/`가 DI로 조립 (Composition Root)

이렇게 하면 domain 레이어가 DB, 프레임워크에 의존하지 않아서 테스트와 교체가 쉬워집니다.

---

## 9. 공유 타입 (common-schemas)

모든 모듈이 공통으로 사용하는 타입은 `packages/common-schemas/`에 단일 정의(SSOT)합니다. 같은 타입을 모듈 내부에서 재정의하면 안 됩니다.

| 타입 | 파일 | 사용 모듈 |
|------|------|----------|
| `WorkflowSchema`, `NodeInstance`, `Edge` | workflow.py | nodes-graph, ai-agent, storage |
| `AgentState`, `IntentResult`, `DraftSpec` | agent.py | ai-agent |
| `DocumentBlock`, `ContentBlock` | document.py | doc-parser |
| `PermissionSource`, `PlaintextCredential` | security.py | auth, toolset |
| `RiskLevel`, `ExecutionStatus` 등 Enum | enums.py | 전 모듈 |
| `SSEFrame`, `AgentNodeFrame` | transport.py | api-server, frontend |

```python
# 올바른 import
from common_schemas import WorkflowSchema, NodeInstance
from common_schemas.enums import RiskLevel, ExecutionStatus
from common_schemas.exceptions import DomainError, ValidationError
```

---

## 10. 자주 하는 실수와 해결책

| 실수 | 왜 문제인가 | 해결책 |
|------|-----------|--------|
| `domain/`에서 `from sqlalchemy import ...` | 도메인이 프레임워크에 결합됨 | `adapters/`에서만 import |
| `from storage.repositories import XRepo` 를 다른 모듈에서 직접 import | 의존성 방향 위반 | `services/api-server/dependencies/`에서 DI로 주입 |
| `WorkflowSchema`를 모듈 내부에서 재정의 | SSOT 위반 | `from common_schemas import WorkflowSchema` |
| API 키를 코드에 하드코딩 | 보안 위반 | `os.getenv("KEY_NAME")` |
| `main`에 직접 PR | 브랜치 전략 위반 | base를 `development`로 설정 |
| 자잘한 수정마다 `feature/fix-*` 브랜치 생성 | 브랜치 과다 생성 | 현재 브랜치에서 커밋, PR만 생성 |
| `docs/context/` 파일을 코드 브랜치에서 수정 | 위키 관리 규칙 위반 | `docs` 브랜치에서 별도 PR |

---

## 11. 기술 스택 요약

| 레이어 | 기술 |
|--------|------|
| 공유 스키마 | Pydantic v2 |
| 백엔드 | FastAPI + Uvicorn |
| 태스크 큐 | Celery + Redis |
| AI 에이전트 | LangGraph |
| LLM | Modal GPU (Gemma 4 + BGE-M3) |
| DB | PostgreSQL + SQLAlchemy + asyncpg + pgvector |
| 프론트엔드 | Next.js 14 + React Flow + Zustand |
| 인프라 | GCP (Cloud Run, Cloud SQL, Secret Manager) + Terraform |
| 코드젠 | pydantic2ts (Python → TypeScript) |

---

## 12. 코딩 컨벤션

- Python >= 3.11
- Ruff lint (line-length=120)
- 타입 힌트 필수 (`def func(x: int) -> str:`)
- 파일명: `snake_case.py`
- 클래스명: `PascalCase`
- ID 필드: `UUID` 타입
- Optional: `Optional[T]` 또는 `T | None` 명시
- Enum: `class Status(str, Enum)` (JSON 호환)
- 테스트: pytest + pytest-asyncio

---

## 13. 참조 문서 모음

| 문서 | 위치 | 용도 |
|------|------|------|
| 이 가이드 | `docs/TEAM_GUIDE.md` | 팀원 실무 워크플로우 |
| Claude Code 지침 | `CLAUDE.md` (루트) | import 규칙, Port/Adapter 매핑, SSOT |
| 각 모듈 README | `modules/*/README.md`, `services/*/README.md` | 모듈별 API, 엔티티, 에러코드, NFR |
| 아키텍처 설계서 | `docs/context/clean_architecture.md` | 전체 아키텍처 |
| 프로젝트 구조 지도 | `docs/context/MAP.md` | 디렉토리/파일 배치 |
| 설계 결정 기록 | `docs/context/decisions.md` | ADR 목록 |
| 클래스 다이어그램 | `docs/class-diagrams/` | 엔티티 관계도 |
| 에이전트 템플릿 | `_agent_templates/` | TDD/리뷰 자동화 |
