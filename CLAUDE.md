# Workflow Automation — Claude Code 지침

## 프로젝트 개요

사내 AI 자동화 스킬 마켓플레이스 플랫폼. Clean Architecture + 모노레포 구조. 사용자가 자연어로 업무 자동화 워크플로우를 요청하면, AI 에이전트가 54종 노드 카탈로그에서 적절한 노드를 조합해 워크플로우를 자동 생성하고, 실행 엔진이 LangGraph StateGraph + TopologicalScheduler(위상 정렬)로 실행한다.

---

## 팀 REQ 배정

| 담당자 | 담당 REQ | 모듈/서비스 |
|--------|----------|------------|
| 황대원 (조장) | REQ-001, 007, 008, 009, 010, 011, 012 | database, execution-engine, storage, api-server, frontend, infra, common-schemas |
| 박아름 | REQ-002, 003 | auth, nodes-graph |
| 신정혜 | REQ-004 | ai-agent |
| 햄햄 | REQ-005 | toolset |
| 김진형 | REQ-006 | doc-parser |

---

## 브랜치 전략

| 브랜치 | 용도 |
|--------|------|
| `main` | 안정 브랜치 (protected, 릴리즈 시점에만 merge) |
| `development` | 통합 브랜치 — feature PR의 base |
| `feature/req-XXX-*` | REQ 단위 기능 개발 |
| `release` | 프로덕션 배포 트리거 |
| `docs` | 문서 전용 (docs/context/ 편집) |

### 커밋 경로 구분

| 변경 유형 | 방식 |
|----------|------|
| REQ 기능 구현/변경 | `feature/req-xxx-*` 브랜치 → development PR (리뷰 후 merge) |
| 자잘한 수정 (문서, 설정, 오타, 디버깅) | 현재 브랜치에서 커밋 → PR (별도 브랜치 생성 불필요, 리뷰는 필수) |
| 안정화/배포 단계 버그 | `hotfix/*` 브랜치 생성 → PR |
| 릴리즈 | `development` → `main` PR (조장 또는 리포 오너가 판단) |

---

## 에이전트 템플릿

TDD 사이클 및 코드 리뷰에 사용하는 에이전트 템플릿은 `_agent_templates/`에 위치한다.

| 에이전트 | 역할 |
|---------|------|
| `ORCHESTRATOR` | TDD 사이클 전체 관리, 에이전트 순서 호출 |
| `TEST_WRITER` | TDD Red — 실패 테스트 작성 |
| `DEVELOPER` | TDD Green — 테스트 통과하는 최소 구현 |
| `TESTER` | 테스트 실행 및 결과 수집 |
| `REFACTOR` | TDD Refactor — 코드 품질 개선 |
| `REVIEW` | 방어적 코드 리뷰 (8축 점검) |
| `REPORTER` | 결과 보고서 생성 |
| `SECURITY_AUDITOR` | 보안 감사 (자격증명/PII 노출 탐지) |
| `IMPACT_ASSESSOR` | PR 전 사후영향 평가 |

---

## 의존성 방향 규칙 (절대 위반 금지)

```
packages/common-schemas/   ← 최내곽 (Pydantic만 의존)
        ↑ import
modules/*/domain/          ← common-schemas + 자기 도메인만 import
        ↑ import
modules/*/application/     ← domain/* + common-schemas (Port 인터페이스만)
        ↑ import
modules/*/adapters/        ← domain/ports + 외부 라이브러리
modules/storage/           ← 다른 모듈의 Port ABC 구현
        ↑ import
services/api-server/       ← 모든 modules/* 조립 (Composition Root)
services/execution-engine/ ← 모든 modules/* 조립
services/frontend/         ← common-schemas/typescript 타입만
```

### 금지 사항

- `domain/` 레이어에서 FastAPI, SQLAlchemy, LangGraph, Celery 등 프레임워크 import 금지
- `application/` 레이어에서 구체 Adapter 직접 import 금지 (Port ABC만 참조)
- ORM 모델(`storage/orm/`)이 도메인 경계를 넘어가는 것 금지
- `modules/` 간 직접 import 시 반드시 상대 모듈의 `domain/ports/` 또는 `domain/entities/`만 참조

---

## 코드 작성 시 README 참조 규칙

각 모듈에 코드를 작성하기 전에 반드시 해당 모듈의 `README.md`를 읽고 따른다.

### 필수 확인 항목

- **import 경로**: README의 Quick Start 섹션에 명시된 import 패턴을 따를 것
- **의존 관계**: README의 "의존 관계" 섹션에서 허용된 의존성만 사용할 것
- **Port 구현 위치**: 인터페이스(ABC)를 정의하는 모듈과 구현하는 모듈이 다름을 인지할 것
- **환경 변수**: 하드코딩 금지, README에 명시된 환경 변수명으로 `os.getenv()` 사용

### README 위치

| 모듈 | README 경로 |
|------|------------|
| common-schemas | `packages/common-schemas/README.md` |
| auth | `modules/auth/README.md` |
| nodes-graph | `modules/nodes-graph/README.md` |
| ai-agent | `modules/ai-agent/README.md` |
| toolset | `modules/toolset/README.md` |
| doc-parser | `modules/doc-parser/README.md` |
| storage | `modules/storage/README.md` |
| api-server | `services/api-server/README.md` |
| execution-engine | `services/execution-engine/README.md` |
| frontend | `services/frontend/README.md` |

---

## 모듈 간 import 규칙

### common-schemas (REQ-012) — 모든 모듈의 기반

```python
from common_schemas import WorkflowSchema, NodeInstance, Edge, Position
from common_schemas import AgentState, DocumentBlock, ContentBlock
from common_schemas import PermissionSource, PlaintextCredential
from common_schemas.enums import AgentMode, ExecutionStatus, RiskLevel, ErrorCode
from common_schemas.exceptions import DomainError, ValidationError, NotFoundError
from common_schemas.transport import SSEFrame, SessionFrame, AgentNodeFrame
```

### modules 간 허용된 교차 import

| 소비자 모듈 | import 가능한 대상 | 구체적 예시 |
|-----------|-----------------|------------|
| ai-agent | auth의 `domain/services` | `from auth.domain.services import CredentialInjectionService` |
| ai-agent | nodes-graph의 `domain/services` | `from nodes_graph.domain.services import GraphValidator` |
| ai-agent | nodes-graph의 `domain/ports` | `from nodes_graph.domain.ports import NodeDefinitionRepository` |
| toolset | auth의 `domain/services` | `from auth.domain.services import CredentialInjectionService` |
| storage | auth의 `domain/ports` | `from auth.domain.ports import SessionRepository` (ABC 구현을 위해) |
| storage | nodes-graph의 `domain/ports` | `from nodes_graph.domain.ports import NodeDefinitionRepository` |
| storage | ai-agent의 `domain/ports` | `from ai_agent.domain.ports import AgentMemoryRepository` |
| execution-engine | toolset의 `application/use_cases` | `from toolset.application.use_cases import ExecuteToolUseCase` |
| execution-engine | nodes-graph의 `domain/services` | `from nodes_graph.domain.services import GraphValidator` |

### 절대 금지 import 패턴

```python
# ❌ domain에서 adapter import
from storage.orm import UserModel  # domain 레이어에서 사용 불가

# ❌ 프레임워크 직접 import (domain/application 레이어에서)
from fastapi import Depends          # services/api-server에서만 허용
from celery import shared_task       # services/execution-engine에서만 허용
from langgraph.graph import StateGraph  # ai-agent/adapters/에서만 허용
from sqlalchemy import Column        # storage/orm/에서만 허용

# ❌ modules 간 adapter 직접 참조
from ai_agent.adapters.llm import ModalAdapter       # 외부에서 참조 불가
from storage.repositories import WorkflowRepository  # services에서만 DI로 조립
```

---

## Port → Adapter 매핑 (DI 참조표)

| Port (ABC) 정의 위치 | Adapter 구현 위치 |
|--------------------|----------------|
| `auth/domain/ports/SessionRepository` | `storage/repositories/` |
| `auth/domain/ports/OAuthConnectionRepository` | `storage/repositories/` |
| `auth/domain/ports/CipherPort` | `auth/adapters/cipher/` |
| `nodes-graph/domain/ports/NodeDefinitionRepository` | `storage/repositories/` |
| `ai-agent/domain/ports/AgentMemoryRepository` | `storage/repositories/` |
| `ai-agent/domain/ports/LLMPort` | `ai-agent/adapters/llm/` |
| `ai-agent/domain/ports/NodeRegistry` | `ai-agent/adapters/` (nodes-graph 퍼사드) |
| `toolset/domain/ports/ToolRegistry` | `toolset/adapters/` |
| `toolset/domain/ports/SecureConnectorPort` | `toolset/adapters/` |
| `doc-parser/domain/ports/ParserPort` | `doc-parser/adapters/parsers/` |

---

## 모듈 내부 표준 구조

모든 도메인 모듈(`modules/*`)은 아래 3계층 구조를 따른다.

```
modules/{module_name}/
├── __init__.py
├── domain/                   # 최내곽 — 순수 비즈니스 로직
│   ├── entities/             #   모듈 전용 도메인 엔티티
│   ├── value_objects/        #   모듈 전용 VO
│   ├── services/             #   도메인 서비스 (순수 비즈니스 규칙)
│   └── ports/                #   인터페이스 정의 (ABC)
├── application/              # 유스케이스 — 도메인 조합 로직
│   └── use_cases/            #   각 유스케이스 = 1 클래스, execute() 메서드
├── adapters/                 # 어댑터 — 외부 시스템 연동
│   └── ...
├── tests/
│   ├── unit/domain/          #   도메인 순수 테스트 (mock 불필요)
│   ├── unit/application/     #   유스케이스 테스트 (Port mock)
│   └── integration/          #   어댑터 통합 테스트
└── README.md                 #   모듈 API 문서 (반드시 참조)
```

---

## 새 코드 작성 절차

1. **README 읽기**: 작업할 모듈의 `README.md`를 먼저 읽는다
2. **의존성 확인**: 위 의존성 방향 규칙에 따라 import 가능 여부 확인
3. **레이어 배치**: 새 클래스/함수가 `domain`, `application`, `adapter` 중 어디에 해당하는지 판단
4. **공유 타입 사용**: 도메인 엔티티/VO/Enum은 반드시 `common-schemas`에서 import
5. **Port 정의/구현 분리**: 인터페이스는 소유 모듈의 `domain/ports/`에, 구현은 `storage/repositories/` 또는 자체 `adapters/`에
6. **보안 점검**: 글로벌 CLAUDE.md 보안 규칙 준수 (하드코딩 금지, `.env` 읽기 금지)

---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 공유 스키마 | Pydantic v2 |
| 백엔드 서버 | FastAPI + Uvicorn |
| 태스크 큐 | Celery + Redis |
| AI 에이전트 | LangGraph |
| LLM | Modal GPU (Gemma 4 + BGE-M3) |
| DB | PostgreSQL + SQLAlchemy + asyncpg + pgvector |
| 프론트엔드 | Next.js 14 + React Flow + Zustand |
| 인프라 | GCP (Cloud Run, Cloud SQL, Secret Manager) + Terraform |
| TypeScript 코드젠 | pydantic2ts |

---

## 컨벤션

- Python >= 3.11, Ruff lint (`line-length=120`)
- 타입 힌트 필수 (모든 함수 시그니처에 타입 명시)
- 테스트: `pytest` + `pytest-asyncio`
- 파일명: `snake_case`
- 클래스명: `PascalCase`
- ID 필드: `UUID` 타입 사용
- Optional 필드: 명시적으로 `Optional[T]` 또는 `T | None`
- Enum: `str` 상속으로 JSON 직렬화 호환 (`class RiskLevel(str, Enum)`)

---

## SSOT 핵심 결정사항

교차분석에서 확정된 핵심 규칙. 코드 구현 시 반드시 준수.

### 공유 타입은 common-schemas에 단일 정의

| 타입 | SSOT 위치 | 자체 정의 금지 모듈 |
|------|----------|-----------------|
| `WorkflowSchema`, `NodeInstance`, `Edge` | `common-schemas/workflow.py` | nodes-graph, ai-agent |
| `AgentState`, `IntentResult`, `DraftSpec` | `common-schemas/agent.py` | ai-agent |
| `DocumentBlock`, `ContentBlock`, `FileMeta` | `common-schemas/document.py` | doc-parser |
| `PermissionSource`, `PlaintextCredential` | `common-schemas/security.py` | auth |
| `RiskLevel`, `AgentMode`, `ExecutionStatus` | `common-schemas/enums.py` | toolset, ai-agent |
| `HandoffPayload`, `EvaluationResult` | `common-schemas/handoff.py` | ai-agent, execution-engine |

### 암호화 도메인 소유권

- `CipherPort(ABC)`는 `auth/domain/ports/`에 정의 — auth 모듈이 소유
- `AESGCMCipher` 구현체는 `auth/adapters/cipher/`에 위치
- 시그니처: `encrypt(bytes) → bytes`, `decrypt(bytes) → bytes`
- `database(REQ-001)`는 DI로 cipher를 주입받아 사용

### Port ↔ 구현체 계약

- Port(ABC) 메서드명/시그니처가 계약 기준
- 구현체(Repository)가 ABC의 메서드명을 따름 (반대 아님)
- Repository는 도메인 엔티티를 반환 — ORM 모델 반환 금지

---

## 주요 실행 흐름

### AI 워크플로우 생성 (REQ-004 → REQ-007)

```
사용자 메시지
  → api-server POST /api/v1/ai/compose (SSE)
  → ai-agent ComposeWorkflowUseCase (13-노드 LangGraph)
    → security_node: 리스크 평가 (auth CredentialInjectionService)
    → intent_node: 의도 분류 (IntentAnalyzerService)
    → retriever_node: 노드 후보 검색 (NodeRegistry → nodes-graph)
    → drafter_node: 초안 생성 (DrafterService)
    → validator_node: 그래프 검증 (GraphValidator, 최대 3회)
    → qa_evaluator_node: 품질 평가 (score ≥ 8 통과)
    → promote_node: 확정
  → WorkflowRepository.save(workflow) → workflow_id
```

### 워크플로우 실행 (REQ-007)

```
api-server POST /api/v1/workflows/{id}/execute
  → Celery task dispatch → execution-engine
  → TopologicalScheduler.schedule() → 병렬 실행 레벨 계산
  → Level 1 노드 병렬 실행
    → ExecuteToolUseCase (REQ-005 외부 도구)
    → LangGraphDispatcher (REQ-004 AI 노드)
  → Level 2 노드 병렬 실행 ...
  → ExecutionRepository에 결과 저장
  → SSE로 프론트엔드에 상태 전파
```

---

## 참조 문서

| 문서 | 위치 |
|------|------|
| 아키텍처 전체 설계 | `docs/context/clean_architecture.md` |
| 프로젝트 구조 지도 | `docs/context/MAP.md` |
| 설계 결정 기록 | `docs/context/decisions.md` |
| 클래스 다이어그램 해결안 | `docs/class_diagram_resolution_proposal.md` |
| 에이전트 템플릿 | `_agent_templates/` (9개) |
