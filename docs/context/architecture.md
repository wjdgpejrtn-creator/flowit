# Architecture

> 프로젝트 전체 아키텍처(4-layer 흐름/경로)를 기술한다.
> 개별 브랜치 내부 구조는 각 브랜치의 `CLAUDE.md`에 둔다.

## 4-Layer 개요

| Layer | 브랜치 | 역할 |
|-------|--------|------|
| Frontend | `Frontend` | 사용자 UI, 워크플로우 편집기 |
| API Server | `API_Server` | FastAPI 기반 REST/WebSocket 엔드포인트 |
| Execution Engine | `Execution_Engine` | 워크플로우 노드 실행 런타임, 디스패처, Agent |
| Database | `Database` | 스키마, 마이그레이션, Repository |

## 데이터 흐름

TODO: 요청 → API → Execution Engine → DB 흐름을 그림/설명으로 기술.

## 경계 및 계약

TODO: 각 레이어 간 인터페이스(요청/응답 스키마, 이벤트, 큐 등) 정의.

## 관련 문서

- 설계 결정 배경: [`decisions.md`](./decisions.md)
- 파일 맵: [`MAP.md`](./MAP.md)
