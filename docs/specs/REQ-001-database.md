# REQ-001 Database — 구현 명세

> **ADR-0012로 책임 확장** (2026-05-14): 본 모듈은 RDB(PostgreSQL)뿐만 아니라
> object storage(GCS, ClamAV) + ORM/Repository/Mapper까지 **모든 영속화 인프라**를
> 담당한다. 기존 REQ-008(storage)의 object storage·Repository 책임이 본 spec으로
> 이전되며, REQ-008은 Skills Marketplace 도메인 전용으로 축소된다. 자세한 결정
> 배경은 `docs/context/adr/ADR-0012-database-storage-module-boundary.md`.

## common_schemas에서 import할 클래스

| 클래스 | 소스 모듈 | 용도 |
|--------|-----------|------|
| `WorkflowSchema` | workflow | ORM ↔ 도메인 모델 변환 기준 |
| `NodeInstance` | workflow | workflow_nodes 테이블 매핑 |
| `NodeConfig` | workflow | node_definitions 테이블 매핑 |
| `Edge` | workflow | workflow_edges 테이블 매핑 |
| `Position` | workflow | NodeInstance.position 컬럼 (JSON) |
| `AgentState` | agent | agent_sessions 테이블 매핑 |
| `DocumentBlock` | document | documents 테이블 매핑 |
| `FileMeta` | document | file_meta JSONB 컬럼 |
| `PermissionSource` | security | user_permissions 테이블 매핑 |
| `ExecutionStatus` | enums | execution_logs.status 컬럼 |
| `ErrorCode` | enums | execution_logs.error_code 컬럼 |

## 이 모듈에서 구현할 클래스

### ORM 모델 (infrastructure/orm/)

| ORM 모델 | 대응 도메인 모델 | 비고 |
|----------|-----------------|------|
| `WorkflowModel` | WorkflowSchema | workflow_id: UUID PK |
| `NodeInstanceModel` | NodeInstance | FK → workflow_id |
| `EdgeModel` | Edge | FK → workflow_id |
| `NodeDefinitionModel` | NodeConfig | node_id: UUID PK |
| `AgentSessionModel` | AgentState | session_id: UUID PK |
| `AgentMemoryModel` | MemoryEntry (REQ-004) | user_id, memory_type (필드명 통일 완료) |
| `DocumentModel` | DocumentBlock | document_id: UUID PK |
| `UserModel` | — | user_id: UUID, role, department_id |
| `CredentialModel` | PlaintextCredential | 암호화 저장, cipher DI |
| `ExecutionLogModel` | — | workflow_id, status, started_at, completed_at |

### Repository 구현체 (infrastructure/repositories/)

REQ-002 ABC 계약을 충족하는 구현체:

| Repository | ABC (REQ-002 정의) | 메서드 |
|------------|-------------------|--------|
| `SessionRepositoryImpl` | SessionRepository | create, find_by_hash, revoke, revoke_all_for_user |
| `OAuthConnectionRepositoryImpl` | OAuthConnectionRepository | create, get_by_credential_id, get_active_for_user, update_tokens, revoke |
| `WorkflowRepositoryImpl` | WorkflowRepository | save, get, list_by_user, delete |
| `NodeDefinitionRepositoryImpl` | NodeDefinitionRepository (REQ-003) | upsert, list_all, get_by_id, search_by_embedding |
| `AgentMemoryRepositoryImpl` | AgentMemoryRepository (REQ-004) | save, list_by_user, search_similar |
| `DocumentRepositoryImpl` | DocumentRepositoryPort (REQ-006) | save, get, list_by_workflow |

### 암호화 (합의사항 H-2)

- **자체 EncryptionStrategy 삭제**
- REQ-002의 `BaseCipher`를 DI로 주입받아 CredentialModel 암/복호화에 사용
- 시그니처: `encrypt(plaintext: bytes) → bytes`, `decrypt(ciphertext: bytes) → bytes`

### 마이그레이션 (raw SQL + `schema_migrations` 추적, ADR-0011)

- PostgreSQL **16** (pgcrypto + pgvector 확장 포함; 자세한 인스턴스 셋업은 `docs/guides/cloud-sql-setup.md`)
- UUID PK 전체 적용
- JSONB 컬럼: NodeInstance.parameters, FileMeta, AgentState.messages
- **Alembic 미도입** — 결정 배경은 `docs/context/adr/ADR-0011-migration-tracking-pattern.md`
- 스키마 파일: `database/schemas/NNN_<name>.sql` (000은 추적 테이블 자체, 001~ 도메인)
- 모든 DDL은 멱등 (`CREATE TABLE/INDEX IF NOT EXISTS`, `CREATE OR REPLACE TRIGGER`)
- **schema 파일은 적용 후 immutable** — 변경은 새 파일로
- 적용 도구: `python -m database.scripts.migrate [--status]`
- 진단 도구: `python -m database.scripts.diagnose`
- IAM 인증 + cloud-sql-python-connector 사용 (DATABASE_URL fallback 가능)
- 운영 절차: `docs/guides/db-migration.md`
- 공유 ownership role `workflow_admin` 패턴: `docs/guides/cloud-sql-setup.md §4-1`

## 합의된 변경사항

| 이슈 | 변경 내용 |
|------|----------|
| H-2 | 자체 cipher 삭제, REQ-002 BaseCipher DI 주입 |
| H-3 | Repository 구현체 메서드명/시그니처를 REQ-002 ABC 기준으로 통일 |
| M-10 | AgentMemoryModel: owner_user_id→user_id, memory_kind→memory_type |

## 의존성 관계

```
upstream:  REQ-002 (ABC 계약), REQ-003 (NodeDefinitionRepository ABC), REQ-004 (AgentMemoryRepository ABC), REQ-006 (DocumentRepositoryPort ABC)
downstream: 모든 모듈 (Repository 구현체 제공)
```
