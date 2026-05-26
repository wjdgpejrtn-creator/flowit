# REQ-008 Storage — 구현 명세

> **ADR-0012 (2026-05-14)**: 본 모듈은 기존 명시된 대로 **영속화 인프라**(RDB
> ORM/Repository/Mapper + object storage 어댑터 + 자체 도메인 `StorageObject`
> 등)를 그대로 담당한다. Skills Marketplace 하위 도메인(§64-72)만 신규
> `modules/skills_marketplace/`로 분리된다 (별도 spec 후속 작성, REQ-013
> 후보). 자세한 결정 배경은
> `docs/context/adr/ADR-0012-database-storage-module-boundary.md`.
>
> **분리 작업 (PR-2d 시점)**:
> - §64-72(Marketplace 하위 도메인)을 `modules/skills_marketplace/`로 이전.
> - 3계층 도메인 엔티티(`PersonalSkill`/`TeamSkill`/`CompanySkill`) + 승격
>   Use Cases(`PromoteToTeamSkillUseCase`, `PromoteToCompanySkillUseCase`) 신설.
> - 단일 `skills` 테이블에서 3계층 분리 마이그레이션.
> - `ai_agent.PersonalSkill`(PR #54) 이름 충돌은 `skills_marketplace` 측이 다른
>   이름 채택으로 해소 (구현 시 옵션 결정).

## common_schemas에서 import할 클래스

| 클래스 | 소스 모듈 | 용도 |
|--------|-----------|------|
| `FileMeta` | document | 업로드 파일 메타데이터 생성/검증 |
| `DocumentBlock` | document | 파싱 결과물 저장 시 타입 참조 |
| `PermissionSource` | security | 파일 접근 권한 검증 |
| `RiskLevel` | enums | 파일 보안 등급 분류 |

## 이 모듈에서 구현할 클래스

### Domain Layer

| 클래스 | 설명 |
|--------|------|
| `StorageObject` | 저장된 파일 엔티티 (object_id, bucket, key, size, content_type, metadata) |
| `UploadPolicy` | 업로드 정책 VO (max_size, allowed_types, virus_scan_required) |
| `StorageEvent` | 이벤트 VO (uploaded, downloaded, deleted, expired) |
| `RetentionPolicy` | 보존 정책 VO (ttl_days, archive_after_days) |

### Port (domain/ports/)

| Port | 메서드 |
|------|--------|
| `ObjectStoragePort` | upload(key, data, metadata)→url, download(key)→bytes (키 부재 시 `NotFoundError(E-STORAGE-001)`), delete(key)→None, presign(key, ttl)→url |
| `VirusScanPort` | scan(data)→ScanResult |
| `StorageEventPort` | emit(event)→None |

### Application Layer

| UseCase | 설명 |
|---------|------|
| `UploadFileUseCase` | 정책 검증 → 바이러스 스캔 → GCS 업로드 → FileMeta 생성 |
| `DownloadFileUseCase` | 권한 검증 → presigned URL 또는 직접 다운로드 |
| `DeleteFileUseCase` | 소유자 검증 → 삭제 → 이벤트 발행 |
| `CleanupExpiredUseCase` | 보존 정책에 따른 만료 파일 정리 (cron) |

### Adapter Layer

| Adapter | 설명 |
|---------|------|
| `GCSAdapter` | Google Cloud Storage 클라이언트 구현. `download` 키 부재 시 `google.cloud.exceptions.NotFound` → `NotFoundError(E-STORAGE-001)`로 정규화(PR #160 — `LocalStorageAdapter`와 일관 contract) |
| `ClamAVAdapter` | 바이러스 스캔 (ClamAV daemon) |
| `LocalStorageAdapter` | 로컬 개발용 파일시스템 저장소 |
| `GcsSkillDocumentStore` | `skills_marketplace.SkillDocumentStore` Port 구현 (ADR-0017 이중 저장 "지침서" 측, PR #160). `ObjectStoragePort` 생성자 주입(production `GCSAdapter`, 테스트 `LocalStorageAdapter` swap). `save(skill_id, doc) → str(gs:// URI)` / `load(skill_id) → SkillDocument \| None`. SKILL.md = YAML frontmatter(name/description) + markdown body(instructions), 키: `skills/{skill_id}/SKILL.md`. production bucket = `SKILLS_MARKETPLACE_BUCKET` (일반 업로드 `GCS_BUCKET_NAME`과 분리) |

### Repository 구현체 (다른 모듈의 Port ABC 구현)

| Repository | 구현하는 Port | 주요 메서드 |
|-----------|-------------|------------|
| `PgSessionRepository` | `auth/domain/ports/SessionRepository` | `create(user_id, session_hash, expires_at: datetime) → Session`, `find_by_hash(hash) → Session`, `revoke(session_id)`, `revoke_all_for_user(user_id) → int` |
| `PgOAuthRepository` | `auth/domain/ports/OAuthConnectionRepository` | `create(user_id, service, tokens) → OAuthConnection`, `get_by_credential_id(id)`, `get_active_for_user(user_id, service)`, `update_tokens(credential_id, tokens)`, `revoke(credential_id)` |
| `PgNodeDefinitionRepository` | `nodes_graph/domain/ports/NodeDefinitionRepository` | `get_by_id(node_id) → Optional[NodeDefinition]`, `list_all(mvp_only) → list[NodeDefinition]`, `search_by_embedding(query, limit) → list[NodeDefinition]`, `upsert(definition) → NodeDefinition` |
| `PgAgentMemoryRepository` | `ai_agent/domain/ports/AgentMemoryRepository` | `save(entry: MemoryEntry) → None`, `find_by_user(user_id, limit) → list[MemoryEntry]`, `find_by_session(session_id: UUID, limit: int) → list[MemoryEntry]` |

> **ai_agent의 `PersonalMemoryStore`(REQ-004 §2.1, Sprint 3 신규)는 storage 모듈에서 구현하지 않는다.** GCS 파일(`gs://workflow-automation-personal/users/{user_id}/MEMORY.md`) 기반이라 RDB Repository 패턴과 다르며, 어댑터는 `modules/ai_agent/adapters/memory/gcs_memory_store.py`에 위치한다. storage 모듈의 `GCSAdapter`(파일 업로드/다운로드 범용 어댑터)와도 별개 — Personalization은 memory.md 포맷 파싱·인덱싱 책임을 직접 가진다.
| `PgWorkflowRepository` | `execution_engine/domain/ports/` | `get(workflow_id: UUID) → WorkflowSchema`, `save(schema: WorkflowSchema) → UUID`, `get_node_config(node_id: UUID) → NodeConfig` |
| `PgExecutionRepository` | `execution_engine/domain/ports/` | `save(row: ExecutionRow) → None`, `get(execution_id: UUID) → ExecutionRow`, `update_node_state(execution_id, state: NodeExecutionState) → None` (transfer-object `ExecutionRow`는 storage 내부 dataclass — 도메인 `ExecutionResult`와 의도적 이름 분리) |
| `PgDocumentRepository` | `doc_parser/domain/ports/` | `save(document: DocumentBlock) → UUID`, `save_chunks(chunks: list[Chunk]) → None`, `save_quality_log(result, document_id) → None` |
| `PgToolExecutionRepository` | `toolset/domain/ports/ToolExecutionRepository` | `save(record: ToolExecutionRecord) → None`, `find_by_tool(tool_name, limit) → list[ToolExecutionRecord]` |
| `PgSkillRepository` | 자체 정의 | `upsert(skill) → Skill`, `get_by_id(skill_id) → Skill`, `list(offset, limit) → list[Skill]`, `search(query, embedding, limit) → list[Skill]` (하이브리드: 0.4×FTS + 0.6×vector) |
| `PgMarketplaceSkillRepository` | `skills_marketplace/domain/ports/SkillRepository` | `save/get_personal·team·company`, `search(query_embedding, scope, limit, include_promoted, lifecycle_state)`, `save_approval(approval)` (ADR-0020 ② 3계층, PR #147 — 구 `PgSkillRepository`와 별개) |

### Marketplace 하위 도메인

| 레이어 | 클래스 | 설명 |
|--------|--------|------|
| domain | `SkillLifecycle` | 상태 머신 (draft→review→approved→published→archived) |
| domain | `ApprovalWorkflow` | 승인 워크플로우 |
| application | `PublishSkillUseCase` | 스킬 발행 |
| application | `SearchSkillsUseCase` | 하이브리드 검색 (0.4×FTS + 0.6×vector) |
| application | `ApproveSkillUseCase` | 스킬 승인 처리 |

## 의존성 관계

```
upstream:  REQ-002 (PermissionSource 권한 검증, SessionRepository/OAuthConnectionRepository ABC),
           REQ-003 (NodeDefinitionRepository ABC),
           REQ-004 (AgentMemoryRepository ABC),
           REQ-005 (ToolExecutionRepository ABC),
           REQ-006 (파싱 대상 원본 파일, DocumentRepositoryPort ABC),
           REQ-012 (common_schemas 도메인 엔티티)
downstream: REQ-006 (원본 파일 읽기), REQ-007 (ExecutionRepository, WorkflowRepository),
            REQ-009 (DI 컨테이너 Repository 주입), REQ-010 (파일 다운로드/미리보기)
infra: GCP Cloud Storage, ClamAV, PostgreSQL + pgvector
```
