# storage

> REQ-008: Repository 구현체, ORM 모델, 도메인↔ORM 매퍼, 파일 저장소, Marketplace 도메인
>
> 구현 명세 → [`docs/specs/REQ-008-storage.md`](../../docs/specs/REQ-008-storage.md)

## 설치

```bash
pip install -e modules/storage
pip install -e "modules/storage[dev]"
```

## Quick Start

```python
from storage.repositories import (
    PgSessionRepository,
    PgOAuthRepository,
    PgNodeDefinitionRepository,
    PgAgentMemoryRepository,
    PgWorkflowRepository,
    PgDocumentRepository,
    PgExecutionRepository,
    PgSkillRepository,
    PgMarketplaceSkillRepository,
    PgToolExecutionRepository,
)
```

## Public API

### repositories/ — Port 구현체 (핵심 export)

| Repository | 구현하는 Port 위치 | 주요 메서드 |
|-----------|-------------------|------------|
| `PgSessionRepository` | `auth/domain/ports/` | `async create(user_id, session_hash, expires_at: datetime) → Session`, `async find_by_hash(hash) → Session`, `async revoke(session_id)`, `async revoke_all_for_user(user_id) → int` |
| `PgOAuthRepository` | `auth/domain/ports/` | `async create(user_id, service, tokens) → OAuthConnection`, `async get_by_credential_id(id)`, `async get_active_for_user(user_id, service)`, `async update_tokens(credential_id, tokens)`, `async revoke(credential_id)` |
| `PgNodeDefinitionRepository` | `nodes_graph/domain/ports/` | `async get_by_id(node_id) → Optional[NodeDefinition]`, `async list_all(mvp_only) → list[NodeDefinition]`, `async search_by_embedding(query, limit) → list[NodeDefinition]`, `async upsert(definition) → NodeDefinition` |
| `PgAgentMemoryRepository` | `ai_agent/domain/ports/` | `save(entry: MemoryEntry) → None`, `find_by_user(user_id, limit) → list[MemoryEntry]`, `find_by_session(session_id, limit) → list[MemoryEntry]` |
| `PgWorkflowRepository` | `execution_engine/domain/ports/` | `get(workflow_id: UUID) → WorkflowSchema`, `save(schema: WorkflowSchema) → UUID`, `get_node_config(node_id: UUID) → NodeConfig` |
| `PgExecutionRepository` | `execution_engine/domain/ports/` | `save(row: ExecutionRow) → None`, `get(execution_id: UUID) → ExecutionRow`, `update_node_state(execution_id, state: NodeExecutionState) → None` (`ExecutionRow`는 storage 측 transfer-object dataclass — 도메인 `ExecutionResult`와 의도적 분리, [[duplicate_code_verify_before_remove]]) |
| `PgDocumentRepository` | `doc_parser/domain/ports/` | `save(document: DocumentBlock) → UUID`, `save_chunks(chunks: list[Chunk]) → None`, `save_quality_log(result, document_id) → None` |
| `PgToolExecutionRepository` | `toolset/domain/ports/` | `save(record: ToolExecutionRecord) → None`, `find_by_tool(tool_name, limit) → list[ToolExecutionRecord]` |
| `PgSkillRepository` | 자체 정의 | `upsert`, `get_by_id`, `list`, `search` (하이브리드) |

### 파일 저장소 (ObjectStorage)

| 포트 | 메서드 | 구현체 |
|------|--------|--------|
| `ObjectStoragePort` | `upload(key, data, metadata) → url` | `GCSAdapter` (프로덕션) |
| | `download(key) → bytes` (키 부재 시 `NotFoundError(E-STORAGE-001)`) | `LocalStorageAdapter` (로컬 개발) |
| | `delete(key) → None` | |
| | `presign(key, ttl) → url` | |
| `SkillDocumentStore` (skills_marketplace Port) | `save(skill_id, SkillDocument) → None`, `load(skill_id) → SkillDocument \| None` | `GcsSkillDocumentStore` — `ObjectStoragePort` 생성자 주입(production GCSAdapter, 테스트 LocalStorageAdapter). SKILL.md = YAML frontmatter(name/description) + markdown body(instructions). 키: `skills/{skill_id}/SKILL.md` (ADR-0017) |

### marketplace/ — 스킬 마켓플레이스 하위 도메인

| 레이어 | 클래스 | 설명 |
|--------|--------|------|
| domain | `SkillLifecycle` | 상태 머신 (draft→review→approved→published→archived) |
| domain | `ApprovalWorkflow` | 승인 워크플로우 |
| application | `PublishSkillUseCase` | 스킬 발행 |
| application | `SearchSkillsUseCase` | 하이브리드 검색 (0.4×FTS + 0.6×vector) |
| application | `ApproveSkillUseCase` | 스킬 승인 처리 |

## 의존 관계

```
Upstream (이 모듈이 의존):
  ├── common_schemas (REQ-012)       → 모든 도메인 엔티티 타입
  ├── auth/domain/ports (REQ-002)    → SessionRepository, OAuthConnectionRepository ABC
  ├── nodes_graph/domain/ports (REQ-003) → NodeDefinitionRepository ABC
  ├── ai_agent/domain/ports (REQ-004)    → AgentMemoryRepository, WorkflowRepository ABC
  ├── toolset/domain/ports (REQ-005)     → ToolExecutionRepository ABC
  └── doc_parser/domain/ports (REQ-006)  → DocumentRepositoryPort ABC

Downstream (이 모듈에 의존):
  ├── api_server (REQ-009)           → DI 컨테이너에서 Repository 주입
  └── execution_engine (REQ-007)     → ExecutionRepository, WorkflowRepository 사용
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `DB_HOST` | Y | PostgreSQL 호스트 |
| `DB_PORT` | N | PostgreSQL 포트 (기본: 5432) |
| `DB_USER` | Y | DB 사용자명 |
| `DB_PASSWORD` | Y | DB 비밀번호 |
| `DB_NAME` | Y | DB 이름 |
| `DB_POOL_SIZE` | N | 커넥션 풀 크기 (기본: 10) |
| `GCS_BUCKET_NAME` | Y | GCS 버킷명 (프로덕션) |

## 설계 규칙

- ORM 모델은 도메인 레이어를 **절대 넘지 않음** (경계 횡단 금지)
- Repository는 Mapper를 사용해 ORM ↔ 도메인 변환 수행
- Repository는 다른 모듈의 Port(ABC)를 구현 — **의존성 역전 원칙**
- 권한 행렬은 Repository SQL `WHERE`로 직접 적용 (애플리케이션 레이어 후처리 금지)
- **임베딩 차원 동기화**: ORM의 `Vector(768)` 컬럼은 현재 BGE-M3(768차원) 기준. 임베딩 모델 변경 시 `node_definition_model.py`, `skill_model.py`, `document_model.py`의 Vector 차원을 반드시 함께 수정할 것

## 비기능 제약

| 항목 | 기준 |
|------|------|
| 마켓플레이스 검색 P95 | < 200ms (top_k=20) |
| 30초 자동 저장 UPDATE | < 50ms |
| scope 권한 위반 | 0건 (SQL 필터 강제) |

## 테스트

```bash
pytest modules/storage/tests/
```
