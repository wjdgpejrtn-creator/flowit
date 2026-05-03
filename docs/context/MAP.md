# Project MAP

> 프로젝트 최상위 폴더 지도. **상위 구조 지도**이지 파일 인덱스가 아니다.
> 새 최상위 폴더가 생길 때만 갱신한다.

## 최상위 구조 (모노레포)

```
Workflow_Automation/
├── packages/                 # 공유 패키지 (common-schemas: REQ-012)
├── services/                 # 배포 가능 서비스
│   ├── api-server/           #   REQ-009: FastAPI Core API
│   ├── execution-engine/     #   REQ-007: Celery Worker + Agent Dispatcher
│   └── frontend/             #   REQ-010: Next.js 14 + React Flow
├── modules/                  # 도메인 모듈 (서비스에서 import)
│   ├── auth/                 #   REQ-002: Auth-Security
│   ├── nodes-graph/          #   REQ-003: 54종 노드 카탈로그
│   ├── ai-agent/             #   REQ-004: LangGraph AI Agent
│   ├── toolset/              #   REQ-005: 8개 Tool + Secure Connector
│   ├── doc-parser/           #   REQ-006: 비정형 문서 처리
│   └── storage/              #   REQ-008: Workflow + Skill + Marketplace
├── database/                 # REQ-001: 스키마(15개) / 마이그레이션 / seeds
├── infra/                    # REQ-011: Terraform + Docker
├── docs/                     # 프로젝트 문서
│   └── context/              #   공용 지식 베이스 (이 위키) — docs 브랜치에서만 편집
├── _agent_templates/         # Claude Agent 템플릿 (9개)
├── scripts/                  # 프로젝트 레벨 스크립트
└── .github/                  # PR 템플릿, CI/CD 워크플로우
```

## 브랜치 전략

| 브랜치 | 용도 |
|--------|------|
| `main` | 안정 브랜치 (protected) |
| `development` | 통합 브랜치 — feature PR의 base |
| `feature/req-XXX-*` | REQ 단위 기능 개발 |
| `release` | 프로덕션 배포 트리거 |
| `docs` | 문서 전용 (`docs/context/` 편집) |

## 관련 문서

- 아키텍처: [`architecture.md`](./architecture.md)
- 설계 결정: [`decisions.md`](./decisions.md)
- 모노레포 구조 상세: [`../../MONOREPO_STRUCTURE.md`](../../MONOREPO_STRUCTURE.md)
