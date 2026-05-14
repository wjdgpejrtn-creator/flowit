# REQ-008 Storage — 구현 명세

> **ADR-0012로 책임 축소** (2026-05-14): 본 모듈은 **Skills Marketplace 도메인
> 전용**으로 재정의된다. 기존의 object storage 어댑터(GCS/ClamAV) + RDB
> Repository 구현체(`PgSessionRepository`, `PgWorkflowRepository` 등)는 모두
> REQ-001(database)로 이전한다. 향후 모듈 디렉토리도 `modules/skills_marketplace/`
> 로 rename 예정. 본 spec의 §13-62는 ADR-0012 머지 후 REQ-001 spec에 흡수되며,
> 본 spec은 §64-72(Marketplace 하위 도메인)만 남기고 **3계층 lifecycle**
> (personal → team → company 승격) 모델로 확장된다. 자세한 결정 배경은
> `docs/context/adr/ADR-0012-database-storage-module-boundary.md`.
>
> **TODO (PR-2d 시점에 본 spec 전면 재작성)**:
> - 3계층 도메인 엔티티: `PersonalSkill`, `TeamSkill`, `CompanySkill`
> - 승격 Use Cases: `PromoteToTeamSkillUseCase`, `PromoteToCompanySkillUseCase`
> - 단일 `skills` 테이블에서 3계층(`personal_skills`/`team_skills`/`company_skills`)
>   분리 마이그레이션
> - `ai_agent.PersonalSkill`(PR #54) 이름 충돌 해소 (PR #54 측 rename)

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
| `ObjectStoragePort` | upload(key, data, metadata)→url, download(key)→bytes, delete(key)→None, presign(key, ttl)→url |
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
| `GCSAdapter` | Google Cloud Storage 클라이언트 구현 |
| `ClamAVAdapter` | 바이러스 스캔 (ClamAV daemon) |
| `LocalStorageAdapter` | 로컬 개발용 파일시스템 저장소 |

### Repository 구현체 (다른 모듈의 Port ABC 구현)

| Repository | 구현하는 Port | 주요 메서드 |
|-----------|-------------|------------|
| `PgSessionRepository` | `auth/domain/ports/SessionRepository` | `create(user_id, session_hash, expires_at: datetime) → Session`, `find_by_hash(hash) → Session`, `revoke(session_id)`, `revoke_all_for_user(user_id) → int` |
| `PgOAuthRepository` | `auth/domain/ports/OAuthConnectionRepository` | `create(user_id, service, tokens) → OAuthConnection`, `get_by_credential_id(id)`, `get_active_for_user(user_id, service)`, `update_tokens(credential_id, tokens)`, `revoke(credential_id)` |
| `PgNodeDefinitionRepository` | `nodes_graph/domain/ports/NodeDefinitionRepository` | `get_by_id(node_id) → Optional[NodeDefinition]`, `list_all(mvp_only) → list[NodeDefinition]`, `search_by_embedding(query, limit) → list[NodeDefinition]`, `upsert(definition) → NodeDefinition` |
| `PgAgentMemoryRepository` | `ai_agent/domain/ports/AgentMemoryRepository` | `save(entry: MemoryEntry) → None`, `find_by_user(user_id, limit) → list[MemoryEntry]`, `find_by_session(session_id: UUID, limit: int) → list[MemoryEntry]` |

> **ai_agent의 `PersonalMemoryStore`(REQ-004 §2.1, Sprint 3 신규)는 storage 모듈에서 구현하지 않는다.** GCS 파일(`gs://workflow-automation-personal/users/{user_id}/MEMORY.md`) 기반이라 RDB Repository 패턴과 다르며, 어댑터는 `modules/ai_agent/adapters/memory/gcs_memory_store.py`에 위치한다. storage 모듈의 `GCSAdapter`(파일 업로드/다운로드 범용 어댑터)와도 별개 — Personalization은 memory.md 포맷 파싱·인덱싱 책임을 직접 가진다.
| `PgWorkflowRepository` | `execution_engine/domain/ports/` | `get(workflow_id: UUID) → WorkflowSchema`, `save(schema: WorkflowSchema) → UUID`, `get_node_config(node_id: UUID) → NodeConfig` |
| `PgExecutionRepository` | `execution_engine/domain/ports/` | `save(result: ExecutionResult) → None`, `get(execution_id: UUID) → ExecutionResult`, `update_node_state(execution_id, state: NodeExecutionState) → None` |
| `PgDocumentRepository` | `doc_parser/domain/ports/` | `save(document: DocumentBlock) → UUID`, `save_chunks(chunks: list[Chunk]) → None`, `save_quality_log(result, document_id) → None` |
| `PgToolExecutionRepository` | `toolset/domain/ports/ToolExecutionRepository` | `save(record: ToolExecutionRecord) → None`, `find_by_tool(tool_name, limit) → list[ToolExecutionRecord]` |
| `PgSkillRepository` | 자체 정의 | `upsert(skill) → Skill`, `get_by_id(skill_id) → Skill`, `list(offset, limit) → list[Skill]`, `search(query, embedding, limit) → list[Skill]` (하이브리드: 0.4×FTS + 0.6×vector) |

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
