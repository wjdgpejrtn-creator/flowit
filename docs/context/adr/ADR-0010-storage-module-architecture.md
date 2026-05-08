# ADR-0010: Storage 모듈 아키텍처 — Mapper 패턴 + 타 모듈 Port ABC 구현

- **Status**: Accepted
- **Date**: 2026-05-07
- **Deciders**: @dhwang0803-glitch
- **Tags**: area/storage, layer/adapter, layer/domain

## Context

Clean Architecture에서 `modules/storage/`는 **Interface Adapter 계층**으로, 다른 모듈(`auth`, `ai_agent`, `nodes_graph`, `toolset`, `doc_parser`)이 `domain/ports/`에 정의한 Repository ABC를 구현하는 역할이다.

기존에는 ORM 모델이 도메인 경계를 넘어가는 안티패턴이 있었고, Repository가 ORM 모델을 직접 반환했다.

## Decision

Storage 모듈을 다음 구조로 구현한다:

### 1. Mapper 패턴 도입

```
modules/storage/
├── orm/                    # SQLAlchemy ORM 모델 (DB 전용)
├── mappers/                # ORM ↔ 도메인 엔티티 변환
├── repositories/           # Port ABC 구현 (pg_*_repository.py)
├── domain/                 # Storage 자체 도메인 (StorageObject, UploadPolicy 등)
├── application/            # Storage 유스케이스 (UploadFile, DeleteFile 등)
├── adapters/               # 외부 스토리지 (GCS, Local, ClamAV)
└── marketplace/            # 마켓플레이스 하위 도메인
```

- `mappers/`가 ORM 모델과 도메인 엔티티 간 변환을 담당
- Repository는 도메인 엔티티만 반환 (ORM 모델 반환 금지)

### 2. 타 모듈 Port ABC 구현 매핑

| Port (ABC) | 구현체 |
|------------|--------|
| `auth/domain/ports/SessionRepository` | `pg_session_repository.py` |
| `auth/domain/ports/OAuthConnectionRepository` | `pg_oauth_repository.py` |
| `nodes_graph/domain/ports/NodeDefinitionRepository` | `pg_node_definition_repository.py` |
| `ai_agent/domain/ports/AgentMemoryRepository` | `pg_agent_memory_repository.py` |
| `ai_agent/domain/ports/WorkflowRepository` | `pg_workflow_repository.py` |
| `toolset/domain/ports/ToolExecutionRepository` | `pg_tool_execution_repository.py` |
| `doc_parser` (향후) | `pg_document_repository.py` |

### 3. Storage 자체 도메인

Storage는 단순 Repository 구현체 외에 자체 도메인 로직을 가진다:
- `StorageObject`, `UploadPolicy`, `RetentionPolicy` 엔티티
- `ObjectStoragePort`, `VirusScanPort`, `StorageEventPort` 포트
- `UploadFileUseCase`, `DeleteFileUseCase`, `CleanupExpiredUseCase`

## Consequences

### Positive
- ORM 모델이 도메인 경계를 넘지 않음 (Clean Architecture 원칙 준수)
- 각 모듈은 자신의 Port ABC만 알면 되고, Storage 내부 구현에 의존하지 않음
- Mapper가 변환 로직을 캡슐화하여 스키마 변경 시 영향 범위 최소화

### Negative / Trade-offs
- Mapper 보일러플레이트 코드 증가 (10개 Mapper 파일)
- ORM 모델과 도메인 엔티티가 유사한 구조를 가지므로 중복감이 있음

### Follow-ups
- `services/api_server/`에서 DI 컨테이너로 Repository 주입 구현 필요 (REQ-009)
- `services/execution_engine/`에서 동일하게 DI 조립 필요 (REQ-007)

## References

- PR #23: `feat(storage): REQ-008 Storage 모듈 전체 구현 + 타 모듈 Port ABC 정합` (Merged)
- PR #26: `fix(cross-module): UtcDatetime 도입 + datetime 안전성 강화`
- CLAUDE.md: Port → Adapter 매핑 (DI 참조표)
