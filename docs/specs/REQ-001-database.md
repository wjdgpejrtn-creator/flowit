# REQ-001 Database — 구현 명세

## common-schemas에서 import할 클래스

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

### 마이그레이션 (alembic/)

- PostgreSQL 15+ (pgvector 확장 포함)
- UUID PK 전체 적용
- JSONB 컬럼: NodeInstance.parameters, FileMeta, AgentState.messages

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
