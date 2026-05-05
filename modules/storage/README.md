# storage

> REQ-008: ORM 모델, Repository 구현체, 도메인↔ORM 매퍼, Marketplace 도메인

## 설치

```bash
pip install -e modules/storage
pip install -e "modules/storage[dev]"
```

## Quick Start

```python
# Repository 구현체 (다른 모듈의 Port를 구현)
from storage.repositories import (
    SessionRepository,
    OAuthRepository,
    NodeDefinitionRepository,
    AgentMemoryRepository,
    WorkflowRepository,
    DocumentRepository,
    ExecutionRepository,
    SkillRepository,
)

# ORM 모델 (직접 import 비권장 — Repository를 통해 접근)
from storage.orm import UserModel, WorkflowModel, ExecutionModel

# 매퍼 (Repository 내부에서 사용)
from storage.mappers import SessionMapper, WorkflowMapper
```

## Public API

### repositories/ — Port 구현체 (핵심 export)

| Repository | 구현하는 Port 위치 | 주요 메서드 |
|-----------|-------------------|------------|
| `SessionRepository` | `auth/domain/ports/` | create, find_by_hash, revoke, revoke_all_for_user |
| `OAuthRepository` | `auth/domain/ports/` | create, get_by_credential_id, get_active_for_user, update_tokens, revoke |
| `NodeDefinitionRepository` | `nodes-graph/domain/ports/` | get_by_id, list_all, search_by_embedding, upsert |
| `AgentMemoryRepository` | `ai-agent/domain/ports/` | save, search(user_id, query, k), delete |
| `WorkflowRepository` | — | get, save, delete, list_by_user |
| `DocumentRepository` | — | save, get |
| `ExecutionRepository` | — | create, get, update_node_result, flush_logs |
| `SkillRepository` | — | upsert, get_by_id, list, search (하이브리드) |

### orm/ — SQLAlchemy 모델

| 모델 | 테이블 | 설명 |
|------|--------|------|
| `UserModel` | users | 사용자 계정 |
| `WorkflowModel` | workflows | 워크플로우 정의 (JSON 직렬화) |
| `NodeInstanceModel` | node_instances | 노드 인스턴스 |
| `ExecutionModel` | executions | 실행 이력 |
| `ChatSessionModel` | sessions | 인증 세션 |
| `OAuthConnectionModel` | oauth_connections | OAuth 연결 |
| `CredentialModel` | credentials | 암호화된 자격증명 |
| `NodeDefinitionModel` | node_definitions | 노드 정의 (1024차원 임베딩 벡터 포함) |
| `AgentMemoryModel` | agent_memories | 에이전트 기억 |
| `DocumentModel` | documents | 파싱된 문서 |
| `SkillModel` | skills | 마켓플레이스 스킬 |
| `ApprovalModel` | approvals | 스킬 승인 |
| `NotificationModel` | notifications | 알림 |
| `AuditLogModel` | audit_logs | 감사 로그 |

### mappers/ — ORM ↔ Domain 변환

| 매퍼 | 변환 방향 |
|------|----------|
| `SessionMapper` | `ChatSessionModel` ↔ `Session` (auth 도메인) |
| `WorkflowMapper` | `WorkflowModel` ↔ `WorkflowSchema` (common-schemas) |
| 기타 | 각 ORM 모델 ↔ 해당 도메인 엔티티 |

### marketplace/ — 스킬 마켓플레이스 하위 도메인

| 레이어 | 클래스 | 설명 |
|--------|--------|------|
| `marketplace/domain/` | `SkillLifecycle` | 상태 머신 (draft→review→approved→published→archived) |
| | `ApprovalWorkflow` | 승인 워크플로우 |
| `marketplace/application/` | `PublishSkillUseCase` | 스킬 발행 |
| | `SearchSkillsUseCase` | 스킬 검색 (하이브리드) |
| | `ApproveSkillUseCase` | 스킬 승인 처리 |

## 의존 관계

```
이 모듈 → common-schemas (모든 도메인 엔티티 타입)
이 모듈 → auth/domain/ports (SessionRepository, OAuthConnectionRepository ABC)
이 모듈 → nodes-graph/domain/ports (NodeDefinitionRepository ABC)
이 모듈 → ai-agent/domain/ports (AgentMemoryRepository ABC)
이 모듈 ← api-server (DI 컨테이너에서 Repository 주입)
이 모듈 ← execution-engine (ExecutionRepository, WorkflowRepository 사용)
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

## Workflow 라이프사이클

| 상태 | 의미 | 전이 트리거 |
|------|------|-----------|
| `draft` | 편집 중. 트리거 등록 X. 마켓플레이스 노출 X | 최초 생성 / Onboarding Consultant 진행 중 |
| `active` | 실행 가능. 트리거 등록 가능 | 사용자 [Save] 클릭 (SchemaValidation 통과 시) |
| `archived` | 읽기 전용. 신규 실행 차단 | 사용자 명시 archive |

- 모든 상태 전이는 단일 atomic 트랜잭션
- archived 상태에서 신규 execution 시도 시 422 거부
- `draft → active` 전이는 REQ-004 SchemaValidation 통과 결과 필수

### 자동 저장 + draft_spec

- Frontend dirty 추적 + 30초 주기 자동 저장 (in-place UPDATE)
- `is_draft=true` 상태에서는 엄격한 DAG 검증 우회
- 사용자 명시 [Save] 시 version 1 증가 + `workflow_versions` 보조 테이블 스냅샷

**`draft_spec` JSONB 표준 구조**:

```json
{
  "natural_language_intent": "주간 보고서를 업로드하면 요약해서 슬랙으로 보내줘",
  "unresolved_nodes": [
    {
      "placeholder_id": "u1",
      "hint": "요약 대상 파일 입력 소스 미결정",
      "candidate_node_types": ["file_upload", "google_drive_list"]
    }
  ],
  "discovered_entities": {
    "target_service": "slack",
    "channel": null,
    "frequency": "weekly"
  },
  "slot_filling_state": {
    "asked": ["channel", "file_source"],
    "pending": ["channel"],
    "filled": {"file_source": "주간보고서.docx"}
  },
  "consultant_turn_count": 3
}
```

## Skill 5 상태 라이프사이클

```
[null] --AI propose--> proposed --[Accept]--> pending_review --[Approve]--> approved
                          \                       \
                           \--[Dismiss/TTL]--> deleted   \--[Reject]--> rejected
                                                         \--[Clarify?]--> needs_clarification --answer--> pending_review
```

| 상태 | 의미 | 다음 상태 / 트리거 |
|------|------|-----------------|
| `proposed` | AI Agent가 등록 제안. 사용자 미확인 | [Accept] → pending_review / [Dismiss] → hard delete / **TTL 7일** → 자동 hard delete |
| `pending_review` | 관리자 / owner 검토 대기 | [Approve] → approved / [Reject] → rejected / [Clarify?] → needs_clarification |
| `approved` | 마켓플레이스 등록 가능 | (deprecation 시 → deprecated_at 설정) |
| `rejected` | 보존되나 라이브러리 기본 필터 숨김 | — |
| `needs_clarification` | follow-up 큐 push 상태 | 답변 수신 → pending_review 자동 복귀 |

- proposed TTL = `skills.proposed_at` 기준 7일. APScheduler 일일 cron으로 자동 hard delete

## Scope 권한 행렬

| scope | 읽기 | 수정 | 삭제 |
|-------|------|------|------|
| Private | owner_user_id == current_user_id | owner | owner |
| Team | owner OR (current_user.department_id ∈ allowed_department_ids) | owner | owner / Admin |
| Public | 전체 사용자 (읽기 전용) | owner / Admin | Admin |

- 권한 행렬은 Repository SQL `WHERE`로 직접 적용 (애플리케이션 레이어 후처리 금지)
- Public 승격은 Admin 승인 필요 → `skill_promotion_logs` 테이블 기록

## 마켓플레이스

### 하이브리드 검색 (FR-008-15)

- `skills.embedding`: vector(1024) + HNSW 인덱스 (BGE-M3)
- PostgreSQL full-text (`to_tsvector('korean', ...)`) + pgvector cosine 결합
- **MVP 가중합**: 0.4 × fts + 0.6 × vector
- 검색 결과는 scope 권한 필터 통과한 skill만 노출

### 인기도 / 활용 통계 (FR-008-16)

`skill_stats` 테이블 (집계 캐시):

| 컬럼 | 용도 |
|------|------|
| `download_count` | 총 다운로드 수 |
| `apply_count_total` | 총 적용 횟수 |
| `apply_count_30d` | 최근 30일 적용 횟수 |
| `unique_applier_count` | 유니크 적용 사용자 수 |
| `avg_rating` | 평균 평점 (1-5) |
| `review_count` | 리뷰 수 |
| `last_applied_at` | 마지막 적용 시각 |

- `hotness_score = z-score(apply_count_30d) + 0.5 × z-score(avg_rating)`
- `skill_stats` 매시간 cron 재집계 (eventual consistency, 최대 1시간 지연 허용)

### 평점 / 리뷰 (FR-008-17)

- `skill_reviews` 테이블: `UNIQUE(skill_id, reviewer_user_id)` — 사용자당 1회
- `CHECK`: reviewer_user_id ≠ skills.owner_user_id (자기 평점 금지)

### 큐레이션 / 버전 / 의존성 (FR-008-19~21)

- `is_featured`, `is_official`, `pinned_until` — Admin만 변경 가능
- `skills.version` (semver TEXT), `deprecated_at`, `replaced_by_skill_id`, `skill_lineage_id`
- `skill_dependencies` 테이블: `kind=hard/soft`, 순환 의존 INSERT 트리거로 차단

### MarketplaceSkillRepository 계약 (FR-008-22)

| 메서드 | 입력 | 출력 |
|--------|------|------|
| `search` | query, scope_filter, category, tags, sort_by, top_k | List[SkillWithScore] (hybrid) |
| `get_with_stats` | skill_id | SkillDetail (skills + skill_stats + recent_reviews top 5) |
| `list_recommended_for_user` | user_id | List[SkillRecommendation] (부서/적용 이력 기반) |
| `list_dependencies` | skill_id | List[SkillDependency] |
| `submit_review` | skill_id, user_id, rating, comment | Review (UNIQUE 멱등) |

## 동시성 / 멱등성

- Workflow 자동 저장 vs 수동 저장 충돌: optimistic locking (`updated_at` 비교)
- Skill approve/reject/propose-accept: `(skill_id, version)` 기반 멱등
- 마켓플레이스 다운로드/적용/평점 제출: 사용자 멱등 키로 트랜잭션 단일화

## 설계 규칙

- ORM 모델은 도메인 레이어를 **절대 넘지 않음** (경계 횡단 금지)
- Repository는 Mapper를 사용해 ORM ↔ 도메인 변환 수행
- Repository는 다른 모듈의 Port(ABC)를 구현 — **의존성 역전 원칙**
- 벡터 검색: `NodeDefinitionModel`에 1024차원 임베딩 컬럼 (pgvector)

## 비기능 제약

| 항목 | 기준 |
|------|------|
| 마켓플레이스 검색 P95 | < 200ms (top_k=20, 1M skills) |
| 30초 자동 저장 in-place UPDATE | < 50ms |
| skill_stats 재집계 cron | 매시간, < 5분 |
| scope 권한 위반 | 0건 (Repository SQL 필터 강제) |
| 마켓플레이스 첫 로드 | Featured + 인기 30일 결과 < 500ms |

## 테스트

```bash
pytest modules/storage/tests/
```
