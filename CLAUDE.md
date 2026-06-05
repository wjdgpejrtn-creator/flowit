# Workflow Automation — Claude Code 지침

## 프로젝트 개요

사내 AI 자동화 스킬 마켓플레이스 플랫폼. Clean Architecture + 모노레포 구조. 사용자가 자연어로 업무 자동화 워크플로우를 요청하면, AI 에이전트가 56종 노드 카탈로그(외부 14 + 도메인 28 + toolset 14)에서 적절한 노드를 조합해 워크플로우를 자동 생성하고, 실행 엔진이 LangGraph StateGraph + TopologicalScheduler(위상 정렬)로 실행한다.

---

## 팀 REQ 배정

| 담당자 | 담당 REQ | 모듈/서비스 | Sprint 3 sub-agent 분장 |
|--------|----------|------------|------------------------|
| 황대원 (조장) | REQ-001, 007, 008, 009, 010, 011, 012 | database, execution_engine, storage, api_server, frontend, infra, common_schemas | — |
| 박아름 (리포 오너) | REQ-002, 003, **013** | auth, nodes_graph, **skills_marketplace** (ADR-0012/0017, 2026-05-20 박아름 이관 확정) | **Skills Builder Agent** |
| 신정혜 | REQ-004 | ai_agent | **Main Orchestrator + Workflow Composer + LLM base** |
| 햄햄 (이가원) | REQ-005 | toolset | **Personalization Agent** |
| 김진형 | REQ-006 | doc_parser | — (SSOT 이관) |

> Sprint 3 (5/11~5/31) 상세 plan: `docs/specs/plan/sprint-3.md`. ai_agent는 단일 책임 원칙 적용한 **멀티 에이전트 구조**(Main Orchestrator + 3 Sub-Agent)로 전환되며, 각 sub-agent는 별도 Modal app으로 배포된다.

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
packages/common_schemas/   ← 최내곽 (Pydantic만 의존)
        ↑ import
modules/*/domain/          ← common_schemas + 자기 도메인만 import
        ↑ import
modules/*/application/     ← domain/* + common_schemas (Port 인터페이스만)
        ↑ import
modules/*/adapters/        ← domain/ports + 외부 라이브러리
modules/storage/           ← 영속화 인프라 — 다른 모듈의 Port ABC 구현 + ORM/object storage
modules/skills_marketplace/ ← Skills Marketplace 도메인 (3계층 personal/team/company, ADR-0012)
database/                  ← 순수 SQL 계층 — DDL · 마이그레이션 · seeds (Python 코드 없음, ADR-0012)
        ↑ import
services/api_server/       ← 모든 modules/* 조립 (Composition Root)
services/execution_engine/ ← 모든 modules/* 조립
services/frontend/         ← common_schemas/typescript 타입만
```

### 금지 사항

- `domain/` 레이어에서 FastAPI, SQLAlchemy, LangGraph, Celery 등 프레임워크 import 금지
- `application/` 레이어에서 구체 Adapter 직접 import 금지 (Port ABC만 참조)
- ORM 모델(`storage/orm/`)이 도메인 경계를 넘어가는 것 금지
- `modules/` 간 직접 import 시 반드시 상대 모듈의 `domain/ports/`, `domain/entities/` 또는 `domain/value_objects/`만 참조 (셋 다 안정 도메인 계층 — use case 입력 계약으로 노출되는 VO 포함)

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
| common_schemas | `packages/common_schemas/README.md` |
| auth | `modules/auth/README.md` |
| nodes_graph | `modules/nodes_graph/README.md` |
| ai_agent | `modules/ai_agent/README.md` |
| toolset | `modules/toolset/README.md` |
| doc_parser | `modules/doc_parser/README.md` |
| storage | `modules/storage/README.md` |
| skills_marketplace | `modules/skills_marketplace/README.md` (ADR-0012/0017, 2026-05-20 뼈대 신설 — 깊이 1) |
| api_server | `services/api_server/README.md` |
| execution_engine | `services/execution_engine/README.md` |
| frontend | `services/frontend/README.md` |

---

## 모듈 간 import 규칙

### common_schemas (REQ-012) — 모든 모듈의 기반

```python
from common_schemas import WorkflowSchema, NodeInstance, Edge, Position
from common_schemas import AgentState, DocumentBlock, ContentBlock
from common_schemas import PermissionSource, PlaintextCredential
from common_schemas.enums import AgentMode, ExecutionStatus, RiskLevel, ErrorCode, IntentType
from common_schemas.exceptions import DomainError, ValidationError, NotFoundError
from common_schemas.transport import SSEFrame, SessionFrame, AgentNodeFrame
```

### modules 간 허용된 교차 import

| 소비자 모듈 | import 가능한 대상 | 구체적 예시 |
|-----------|-----------------|------------|
| ai_agent | auth의 `domain/services` | `from auth.domain.services import CredentialInjectionService` |
| ai_agent | auth의 `domain/ports` | `from auth.domain.ports import OAuthConnectionRepository` (`OAuthConnectionResolver` 어댑터가 `ConnectionResolver` 구현 시 — 사용자 보유 connection을 credential로 해소해 노드 선바인딩, PR #348) |
| ai_agent | nodes_graph의 `domain/services` | `from nodes_graph.domain.services import GraphValidator` |
| ai_agent | nodes_graph의 `domain/ports` | `from nodes_graph.domain.ports import NodeDefinitionRepository` |
| ai_agent | nodes_graph의 `application/executable_node_types` | `from nodes_graph.application.executable_node_types import EXECUTABLE_NODE_TYPES` (Composer retriever가 후보를 실행 가능 node_type으로 그라운딩. **import-safe 상수 미러** — 무거운 `get_all_node_classes`(노드 클래스 deps) 미import. PR #387 #378) |
| auth | nodes_graph의 `domain/ports` | `from nodes_graph.domain.ports import NodeDefinitionRepository` (CredentialInjectionService가 `required_connections` / `risk_level` 검증 시) |
| toolset | auth의 `domain/services` | `from auth.domain.services import CredentialInjectionService` |
| toolset | nodes_graph의 `application/use_cases` | `from nodes_graph.application.use_cases import SearchNodesUseCase` (NodeSearchPort 구현체가 자연어 노드 검색 시. **선반영** — 현재 `modules/toolset/` 실코드 0건, 박아름 후속 PR(toolset 정리) + 햄햄 NodeSearchPort 구현 시 도달) |
| storage | auth의 `domain/ports` | `from auth.domain.ports import SessionRepository` (ABC 구현을 위해) |
| storage | auth의 `domain/entities` | `from auth.domain.entities import User` (PgUserRepository 구현체가 ORM ↔ 도메인 변환 시, PR #87 cef92fa) |
| storage | nodes_graph의 `domain/ports` | `from nodes_graph.domain.ports import NodeDefinitionRepository` |
| storage | ai_agent의 `domain/ports` | `from ai_agent.domain.ports import AgentMemoryRepository` |
| storage | skills_marketplace의 `domain/ports` | `from skills_marketplace.domain.ports import SkillRepository` (ABC 구현을 위해 — ADR-0017 + 5/20 합의: Port 정의는 skills_marketplace, 구현은 storage) |
| skills_marketplace | nodes_graph의 `domain/ports` | `from nodes_graph.domain.ports import NodeDefinitionRepository` (스킬 ↔ 노드 카탈로그 연결) |
| ai_agent | skills_marketplace의 `application/use_cases` | `from skills_marketplace.application.use_cases import SearchSkillsUseCase` (Composer가 노드 후보 검토 시) |
| ai_agent | skills_marketplace의 `domain/value_objects` | `from skills_marketplace.domain.value_objects import NodeSpecStaging` (Skills Builder가 `CreateDraftSkillUseCase` 입력 계약 VO 생성 시 — ADR-0020 ③-a wizard, PR #151) |
| execution_engine | toolset의 `application/use_cases` | `from toolset.application.use_cases import ExecuteToolUseCase` |
| execution_engine | nodes_graph의 `domain/services` | `from nodes_graph.domain.services import GraphValidator` |
| execution_engine | skills_marketplace의 `domain/ports` | `from skills_marketplace.domain.ports import SkillDocumentStore` (CatalogNodeExecutor가 LLM 노드 실행 시 바인딩 SkillDocument 지침서를 `load()`해 system 프롬프트에 주입 — REQ-013 런타임 주입, 구현체 `GcsSkillDocumentStore`는 container에서 주입) |

### 절대 금지 import 패턴

```python
# ❌ domain에서 adapter import
from storage.orm import UserModel  # domain 레이어에서 사용 불가

# ❌ 프레임워크 직접 import (domain/application 레이어에서)
from fastapi import Depends          # services/api_server에서만 허용
from celery import shared_task       # services/execution_engine에서만 허용
from langgraph.graph import StateGraph  # ai_agent/adapters/에서만 허용
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
| `auth/domain/ports/UserRepository` | `storage/repositories/` (PR #87 cef92fa) |
| `auth/domain/ports/CredentialRepository` | `storage/repositories/` (PR #99 — oauth_connections.credential_id FK 대상) |
| `auth/domain/ports/CipherPort` | `auth/adapters/cipher/` |
| `nodes_graph/domain/ports/NodeDefinitionRepository` | `storage/repositories/` |
| `ai_agent/domain/ports/AgentMemoryRepository` | `storage/repositories/` |
| `ai_agent/domain/ports/LLMPort` | `ai_agent/adapters/llm/` (Modal Gemma 4) |
| `nodes_graph/domain/ports/EmbedderPort` | `ai_agent/adapters/llm/` (Modal BGE-M3, **예외 패턴** — Port 소유 모듈(nodes_graph)이 아닌 외부 모듈(ai_agent)이 구현체 소유. PR #30 2026-05-12 결정: Modal 호출은 ai_agent 영역) |
| `ai_agent/domain/ports/PersonalMemoryStore` | `ai_agent/adapters/memory/` (GCS, Sprint 3 신규) |
| `ai_agent/domain/ports/NodeRegistry` | `ai_agent/adapters/` (nodes_graph 퍼사드) |
| `toolset/domain/ports/ToolRegistry` | `toolset/adapters/` |
| `toolset/domain/ports/SecureConnectorPort` | `toolset/adapters/` |
| `doc_parser/domain/ports/ParserPort` | `doc_parser/adapters/parsers/` |
| `skills_marketplace/domain/ports/SkillRepository` | `storage/repositories/` (ADR-0017 + 5/20 합의 — Port 소유 skills_marketplace, 구현 storage. `PgMarketplaceSkillRepository`, PR #147) |
| `skills_marketplace/domain/ports/SkillDocumentStore` | `storage/adapters/` (`GcsSkillDocumentStore` — `ObjectStoragePort` 조합, `save()→str(gs:// URI)`, `SKILLS_MARKETPLACE_BUCKET`. PR #160. ADR-0017 SkillDocument GCS 이중 저장) |

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
4. **공유 타입 사용**: 도메인 엔티티/VO/Enum은 반드시 `common_schemas`에서 import
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

- Python >= 3.12, Ruff lint (`line-length=120`)
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

### 공유 타입은 common_schemas에 단일 정의

| 타입 | SSOT 위치 | 자체 정의 금지 모듈 |
|------|----------|-------------------|
| `WorkflowSchema`, `NodeInstance`, `Edge` | common_schemas/workflow.py | nodes_graph, ai_agent |
| `AgentState`, `IntentResult`, `DraftSpec` | common_schemas/agent.py | ai_agent |
| `DocumentBlock`, `ContentBlock`, `FileMeta` | common_schemas/document.py | doc_parser |
| `Chunk`, `ChunkingStrategy`, `QualityGateResult`, `QualityMetrics`, `ParseCoverage`, `WarningInfo` | common_schemas/document.py | doc_parser, ai_agent, storage (REQ-012 이관 완료, common_schemas 0.11.0 — doc_parser는 shim 재노출) |
| `PermissionSource`, `PlaintextCredential` | common_schemas/security.py | auth |
| `RiskLevel`, `AgentMode`, `ExecutionStatus`, `IntentType` | common_schemas/enums.py | toolset, ai_agent |
| `HandoffPayload`, `EvaluationResult` | common_schemas/handoff.py | ai_agent, execution_engine |

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
  → api_server POST /api/v1/ai/compose (SSE)
  → ai_agent ComposeWorkflowUseCase (13-노드 LangGraph)
    → security_node: 리스크 평가 (auth CredentialInjectionService)
    → intent_node: 의도 분류 (IntentAnalyzerService)
    → retriever_node: 노드 후보 검색 (NodeRegistry → nodes_graph)
    → drafter_node: 초안 생성 (DrafterService)
    → validator_node: 그래프 검증 (GraphValidator, 최대 3회)
    → qa_evaluator_node: 품질 평가 (score ≥ 8 통과)
    → promote_node: 확정
  → WorkflowRepository.save(workflow) → workflow_id
```

### 워크플로우 실행 (REQ-007)

```
api_server POST /api/v1/workflows/{id}/execute
  → Celery task dispatch → execution_engine
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
