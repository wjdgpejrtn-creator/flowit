# Workflow Automation

사내 AI 자동화 스킬 마켓플레이스 플랫폼 (Gemma 4 Hackathon)

## Quick Start

```bash
# 로컬 인프라
docker compose -f infra/docker/docker-compose.dev.yml up -d postgres redis

# API 서버
pip install -e packages/common-schemas/python -e services/api-server[dev]
uvicorn app.main:app --reload --app-dir services/api-server

# 프론트엔드
cd services/frontend && npm install && npm run dev
```

## Structure

자세한 구조는 [`MONOREPO_STRUCTURE.md`](./MONOREPO_STRUCTURE.md) 참조.

| 디렉토리 | 설명 |
|---|---|
| `packages/` | 공유 패키지 (Pydantic v2 → TypeScript SSOT) |
| `services/` | 배포 가능 서비스 (api-server, execution-engine, frontend) |
| `modules/` | 도메인 모듈 (auth, nodes-graph, ai-agent, toolset, doc_parser, storage) |
| `database/` | PostgreSQL 스키마 (15개) + 마이그레이션 |
| `infra/` | Terraform + Docker |

## Tech Stack

- **Backend**: Python 3.11 · FastAPI · Celery · LangGraph
- **Frontend**: Next.js 14 · React Flow · Zustand
- **AI**: Gemma 4 (Modal L4 GPU) · BGE-M3
- **DB**: PostgreSQL 16 + pgvector · Redis 7
- **Infra**: GCP Cloud Run · Cloud SQL · Memorystore · GCS · Terraform
