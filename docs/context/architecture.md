# Architecture

> 프로젝트 전체 아키텍처(4-layer 흐름/경로)를 기술한다.
> 모노레포 디렉토리 구조 상세는 [`MONOREPO_STRUCTURE.md`](../../MONOREPO_STRUCTURE.md) 참조.

## 4-Layer 개요

```
┌──────────────────────────────────────────────────────┐
│ Frontend Layer         services/frontend/    REQ-010  │
│   Next.js 14 + React Flow + Zustand                  │
├──────────────────────────────────────────────────────┤
│ Core API Layer         services/api-server/  REQ-009  │
│   FastAPI 라우터 / DI / SSE 중계                       │
├──────────────────────────────────────────────────────┤
│ Domain Layer           modules/                       │
│   auth (REQ-002) · nodes-graph (REQ-003)              │
│   ai-agent (REQ-004) · toolset (REQ-005)              │
│   doc-parser (REQ-006)                                │
│   + services/execution-engine/ (REQ-007)              │
├──────────────────────────────────────────────────────┤
│ Persistence Layer                                     │
│   database/ (REQ-001) · modules/storage/ (REQ-008)   │
│   PostgreSQL 16 + pgvector + Redis + GCS              │
├──────────────────────────────────────────────────────┤
│ Foundation                                            │
│   packages/common-schemas/ (REQ-012)                  │
│   infra/ (REQ-011)                                    │
└──────────────────────────────────────────────────────┘
```

## 데이터 흐름 (대표 시나리오)

```
[사용자 채팅] "주간 보고서를 요약해서 슬랙으로"
     ↓ (Frontend SSE 설정)
[services/frontend] ChatPanel → POST /api/v1/ai/compose?stream=true
     ↓
[services/api-server] Router → 권한 검증 (modules/auth) + Permission Source 주입
     ↓
[modules/ai-agent] LangGraph: security → onboarding → intent → retriever → drafter ↔ validator
     ↓ [SSE] result.intent=draft
[services/frontend] 캔버스에 적용
     ↓ (사용자 [Save])
[services/api-server] POST /api/v1/workflows → [modules/storage] 저장
     ↓ (사용자 [Execute])
[services/execution-engine] execute_workflow.delay() → Celery Worker
     ↓ (노드별)
[modules/toolset] Secure Connector → Google Drive / Gemma4 / Slack API
     ↓ (database/ node_logs flush)
[services/api-server] 폴링 → [services/frontend] ResultDrawer 렌더
```

## 경계 및 계약

| 경계 | 인터페이스 | 스키마 SSOT |
|------|-----------|-------------|
| Frontend ↔ API | REST + SSE | `packages/common-schemas/typescript/` |
| API ↔ Domain Modules | Python import | `packages/common-schemas/python/` |
| API ↔ Execution Engine | Celery task queue (Redis) | `packages/common-schemas/python/` |
| Domain ↔ Persistence | Repository 패턴 | `modules/storage/repositories/` |
| Execution Engine ↔ Tools | Tool 인터페이스 | `modules/toolset/tools/` |

## 관련 문서

- 설계 결정 배경: [`decisions.md`](./decisions.md)
- 파일 맵: [`MAP.md`](./MAP.md)
- 모노레포 구조: [`../../MONOREPO_STRUCTURE.md`](../../MONOREPO_STRUCTURE.md)
