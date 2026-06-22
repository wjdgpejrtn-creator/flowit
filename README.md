# FlowIt — Multi-Agent Agentic Workflow Automation Platform

> **"암묵지를 시스템 속 스킬로, 스킬을 워크플로우로 AI가 만들고 하네스가 품질을 보장한다"**

자연어 요청을 AI 에이전트가 62종 노드 카탈로그에서 조합하여 워크플로우를 자동 생성·검증·실행하는 멀티에이전트 플랫폼.
업무 문서(SOP)를 올리면 AI가 재사용 가능한 Skill로 변환하고, 온톨로지 GraphRAG로 노드 선택 품질을 보장합니다.

**5인 팀 · 4 Sprint (2026.05–06)**

담당: **PM · 백엔드 · 프론트엔드** — 스프린트 일정·협업 주도, 아키텍처 설계, AI Native 하니스 엔지니어링, 멀티에이전트 오케스트레이션

[![Portfolio](https://img.shields.io/badge/Portfolio-dhwang0803--glitch.vercel.app-000000?style=flat-square&logo=vercel&logoColor=white)](https://dhwang0803-glitch.vercel.app/projects/flowit)

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
- [포트폴리오 상세](https://dhwang0803-glitch.vercel.app/projects/flowit)

---

## Team

| 이름 | 역할 |
|------|------|
| 황대원 | **PM · 백엔드 · 프론트엔드** |
| 김진형 | 백엔드 |
| 이가원 | 백엔드 · 프론트엔드 |
| 박아름 | 백엔드 |
| 신정혜 | 백엔드 |

**기간**: 2026.05 ~ 06 (5인, 4 Sprint)
