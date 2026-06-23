# FlowIt — Multi-Agent Agentic Workflow Automation Platform

> **"암묵지를 시스템 속 스킬로, 스킬을 워크플로우로 AI가 만들고 하네스가 품질을 보장한다"**

자연어 요청을 AI 에이전트가 62종 노드 카탈로그에서 조합하여 워크플로우를 자동 생성·검증·실행하는 멀티에이전트 플랫폼.
업무 문서(SOP)를 올리면 AI가 재사용 가능한 Skill로 변환하고, 온톨로지 GraphRAG로 노드 선택 품질을 보장합니다.

**5인 팀 · 4 Sprint (2026.05–06)**

담당: **AI Agent (REQ-004)** — Main Orchestrator · Workflow Composer · LLM Base 설계·구현. LangGraph supervisor 라우팅 결정형 분리, tool-calling/DAG 에이전트 구현, Modal GPU 멀티에이전트 분리 배포, 자체 호스팅 Gemma 4 추론 안정화.

---

## Demo

https://github.com/user-attachments/assets/demo.mp4

> 데모 영상이 보이지 않으면 [`assets/demo.mp4`](./assets/demo.mp4)에서 직접 확인할 수 있습니다.

---

## Key Results

| 지표 | Before (벡터만) | After (GraphRAG) |
|------|:-:|:-:|
| 끊긴 워크플로우 비율 | **23.2%** | **0.0%** |
| 생성 품질 (QA pass) | 0.45 | **0.75** |
| motif-correctness | 75% | **100%** |
| 노드 풍부화 | 3.0 | **3.25** |

---

## Architecture

### System Overview

```
요청 (자연어)
  └─ Frontend (Next.js · React Flow)
       └─ api_server (FastAPI · Composition Root)
            └─ orchestrator (Supervisor 루프 · 9종 intent 분류)
                 ├─ Composer       — LangGraph + GraphRAG · 22노드 fixed DAG
                 ├─ Skills Builder — 문서 → 스킬 (HITL)
                 ├─ Personalization — 메모리 (GCS + CAS)
                 ├─ fast_response  — 즉시 응답 (LLM 0~1회)
                 └─ llm-base       — Gemma 4 + BGE-M3 공통 추론
                      ├─ PostgreSQL 16 + pgvector (정형 · 벡터)
                      ├─ Neo4j AuraDB (온톨로지 그래프)
                      └─ GCS (파일 · 세션 · 메모리)
```

### Clean Architecture · 모노레포

의존성은 항상 안쪽(common_schemas)으로만 — 모듈·LLM·DB 교체 시 핵심 로직 무변경.

```
Layer 1 — CONTRACT    common_schemas (Python · TS 타입 SSOT)
Layer 2 — MODULES     modules/*/domain · application · adapters (Hexagonal)
Layer 3 — ASSEMBLY    services/ = Composition Root (api_server · frontend · agents)
```

### Multi-Agent (Supervisor + 3 Sub-Agent · 5 Modal App)

| Modal App | 역할 |
|-----------|------|
| `orchestrator` | Supervisor · intent 분류 · 라우팅 |
| `agent-composer` | 워크플로우 생성 (LangGraph + 온톨로지) |
| `agent-skills-builder` | 문서 → 스킬 (HITL) |
| `agent-personalization` | 메모리 (GCS + CAS) |
| `llm-base` | Gemma 4 + BGE-M3 공통 추론 |

### Ontology GraphRAG

평탄 벡터 검색의 한계(노드 호환성·필수 연결 미반영)를 Neo4j 그래프 확장으로 해소:

```
vector seed (pgvector)
  → 1-hop expand (CAN_FOLLOW)
    → ground truth 허용집합
      → 제약 후보
        → 결정적 조립 (skeleton)
          → 2중 검증 (LLM-as-Judge QA ≥ 8 + GraphValidator 7종)
```

---

## Core Features

### 1. Workflow Composer
자연어 요청을 22개의 툴로 워크플로우를 조립하는 에이전트. Planning → Tool-Calling → Action → Evaluation 4요소 사이클.

### 2. Skills Builder
업무 문서(SOP)를 재사용 가능한 스킬로 변환. 2단계 추출(메타 → 상세), 결정적 스켈레톤, 2-md(SKILL.md + COMPOSER.md) 이중 저장.

### 3. Skills Marketplace
개인 → 팀 → 회사 3-scope 승격. 산업 6 · 직무 5 시드 스킬. RBAC · fail-closed.

### 4. Node Catalog
62종 노드 · 8 카테고리 · GraphValidator 7종(유한순환 허용). 실행엔진과 1:1 미러.

### 5. Execution Engine
TopologicalScheduler (비순환 → 위상정렬) + CyclicScheduler (Tarjan SCC → 반복 · max 10). 조건문·제어문·검증 루프 모두 지원 — 단순 DAG가 아닙니다.

---

## Tech Stack

| Category | Stack |
|----------|-------|
| **Language** | Python 3.12 · TypeScript |
| **Backend** | FastAPI · Uvicorn · Celery · Redis |
| **Frontend** | Next.js 14 · React Flow · Zustand |
| **AI** | Gemma 4 (Modal L4 GPU) · BGE-M3 · LangGraph |
| **Database** | PostgreSQL 16 + pgvector (HNSW) · Neo4j AuraDB · Redis 7 |
| **Schema** | Pydantic v2 → TypeScript 자동 코드젠 (pydantic2ts) |
| **Infra** | GCP Cloud Run · Cloud SQL · Memorystore · GCS · Terraform (7 모듈) |
| **CI/CD** | PR 게이트 3종 (drift 감지 · pytest 94+ · Ruff lint) → Workload Identity 배포 |
| **Code Standard** | Ruff (line-length=120) · 타입 힌트 전 함수 필수 · pytest + pytest-asyncio |

---

## Harness Engineering

TDD 자동화 하네스 Red → Green → Refactor — 9종 에이전트시스템.

- **Orchestrator** 중심 8종 전문 에이전트 (Developer · Tester · Test Writer · Security · Review · Refactor · Reporter · Impact)
- **클로드코드 규칙 강제**: Clean Architecture 의존성 단방향 · `common_schemas` 단일 진실원 · 변경 가드레일
- **컨텍스트 엔지니어링**: `docs` 브랜치 위키피디아 생태계 · 브랜치별 컨텍스트 · 타입 일치 보장

---

## Project Management

- **4 Sprint** 운영 (요구사항 정의 → 구조 설계 → 핵심 기능 구현 → 통합 및 보완)
- **Jira Calendar** 기반 Sprint 범위·마감일 고정, 산출물 반복 개선
- **GitHub PR + Slack** 피드백 연결 협업 흐름

---

## 내 역할 — 신정혜 · REQ-004 `ai_agent`

**Main Orchestrator + Workflow Composer + LLM Base** 담당. 자연어 요청을 의도 분류 →
라우팅 → 워크플로우 자동 생성까지 잇는 멀티에이전트 코어를 설계·구현했습니다.

### 1. Main Orchestrator (`orchestrator`)
- LangGraph **Supervisor 패턴**으로 3개 Sub-Agent(Composer · Skills Builder · Personalization) 라우팅
  — `load_memory → analyze_intent → route → relay → update_memory`
- **라우팅을 LLM이 아닌 결정형 순수 함수로 분리** — intent → 레시피 키 → `RoutePlan` 큐.
  재현 가능 · 단위 테스트 가능 (`make_plan` · `route` · `recovery_target`)
- 복합 의도(`skill_then_compose`) 순차 디스패치 + **state-mediated 핸드오프**(sub-agent 직접 통신 0)
- 견고성: **무한 루프 3중 방어**(MAX_HOPS · retry · review-guard) · relay 복구 루프
  (연결 사전 실패 ErrorFrame 억제 → 재시도) · httpx **SSE 스트리밍** + OpenTelemetry `trace_id` 전파

### 2. Workflow Composer (`agent-composer`)
- LangGraph `StateGraph` **fixed DAG**: `security → intent → retriever → drafter →
  validator → QA → promote` (전 단계 SSE 스트리밍)
- **Clean Architecture 준수** — LangGraph는 adapter, 비즈니스 규칙은 의존성 0의 순수 도메인 서비스
- `security`: 프롬프트 인젝션 차단 / `retriever`: 의미검색 + **GraphRAG CAN_FOLLOW 확장** +
  구조·핵심 LLM 노드 항상-포함 + 개인 패턴 RAG / `qa`: **LLM-as-Judge(≥8) + 의도-노드 커버리지 게이트**
- 데이터흐름 `${node.field}` 참조 배선 및 **상류 스키마 grounding**(환각 필드 교정), ref 기반 refine 편집

### 3. LLM Base (`llm-base`)
- `LLMPort` 구현 — **자체 호스팅 Gemma 4 (Modal L4 GPU)** 공통 추론 (외부 LLM 미사용)
- 구조적 출력(`generate_structured`): JSON-schema grammar + 3회 재시도 + 코드펜스/취소 sentinel 가드 +
  토큰 예산으로 컨텍스트 초과 방지

### 핵심 챌린지 → 해결
| 문제 | 해결 |
|------|------|
| 작은 LLM의 structured JSON 잘림 (후보 풀 비대 시 품질 급락) | 프롬프트 다이어트(후보 cap · slim schema · 우선 카테고리 보존) |
| 상태 의존 의도(draft↔refine)를 텍스트로 분류 불가 | `has_pending_draft` **편집 잠금**으로 결정적 해소 |
| QA가 만점 주며 "노드 추가" 자기모순 + `["none"]` 센티넬 | 의도-노드 게이트로 점수↔판정 정합 + 센티넬 필터 |
| 의미검색이 트리거·generic LLM 노드 누락 | 관련도 무관 **항상-포함** 합산 |

> **요지**: 자체 호스팅 소형 LLM(Gemma)의 한계를 *측정* 으로 규명하고, 비결정성을
> **결정형 가드레일**로 감싸 신뢰성 있는 워크플로우 자동 생성을 달성.

---

## Monorepo Structure

자세한 구조는 [`MONOREPO_STRUCTURE.md`](./MONOREPO_STRUCTURE.md) 참조.

| 디렉토리 | 설명 |
|---|---|
| `common_schemas/` | 공유 타입 SSOT (Python + TS) |
| `modules/` | 도메인 모듈 (ai_agent · auth · nodes_graph ...) |
| `services/` | 배포 단위 (api_server · frontend · agents) |
| `database/` | 순수 SQL (DDL · 마이그레이션) |
| `infra/` | Terraform (7 모듈) + Docker |

---

## Quick Start

```bash
# 로컬 인프라
docker compose -f infra/docker/docker-compose.dev.yml up -d postgres redis

# API 서버
pip install -e packages/common_schemas/python -e services/api_server[dev]
uvicorn app.main:app --reload --app-dir services/api_server

# 프론트엔드
cd services/frontend && npm install && npm run dev
```

---

## Documents

- [발표자료 (PDF)](./assets/FlowIt.pdf)

---

## Team

| 이름 | 역할 |
|------|------|
| 황대원 | PM · 백엔드 · 프론트엔드 |
| 김진형 | 백엔드 |
| 이가원 | 백엔드 · 프론트엔드 |
| 박아름 | 백엔드 |
| 신정혜 | **백엔드 (AI Agent · REQ-004)** — Main Orchestrator · Workflow Composer · LLM Base |

**기간**: 2026.05 ~ 06 (5인, 4 Sprint)