# ADR-0012: `database/` ↔ `modules/storage/` 책임 재정의 — 영속화 인프라 vs Skills Marketplace 도메인

- **Status**: Accepted
- **Date**: 2026-05-14
- **Deciders**: @dhwang0803-glitch (REQ-001 / 조장)
- **Tags**: area/architecture, area/database, area/storage, layer/infrastructure, layer/domain

## Context

REQ-001(database) / REQ-008(storage) 두 spec의 책임 경계가 코드 진척 과정에서 흐려졌다. 본 ADR 직전(2026-05-14, PR #61 머지 직후) 상태를 정리하면:

1. **REQ-008(storage) spec이 잡탕 구조** — `StorageObject` 도메인 + `GCSAdapter`/`ClamAVAdapter` 같은 object storage 어댑터(§13-46) + 다른 모듈 Port 구현체(`PgSessionRepository`, `PgWorkflowRepository` 등 §48-62) + Marketplace 하위 도메인(§64-72) 세 책임이 한 모듈에 묶여 있다.
2. **REQ-001(database) spec은 "순수 SQL 계층"으로 제한**(`docs/context/clean_architecture.md §8.1` "Python 코드 의존 없음")으로 정의됐지만 현실은 `database/src/models/` (27 ORM) + `database/src/repositories/` (19 Repository) + `database/src/helpers/` (CipherProtocol·SessionManager·CredentialStore)가 들어가 있다.
3. **ORM이 두 군데에서 서로 다른 정의로 중복** — 같은 테이블(`workflows`, `agent_memories` 등)에 대해 `database/src/models/`와 `modules/storage/orm/`가 컬럼/FK/인덱스가 다른 모델을 각각 정의. 일부(`modules/storage/orm/workflow_model.py`)는 실제 schema와도 어긋남 (`user_id` 컬럼 누락).
4. **PR #54(Personalization)의 `PersonalSkill` 엔티티가 Marketplace 컨텍스트의 `personal_skills`와 이름 충돌** — 전자는 사용자 패턴/기억(`memory.md` 본문), 후자는 워크플로우 자동화 스킬 노드. 도메인 의미 완전 다름.
5. **Skills Marketplace의 3계층 lifecycle**(personal → team → company 승격)은 spec 합의 당시 구체화되지 않아 현행 schema(`005_skill_bootstrap.sql` + `013_marketplace.sql`)에 단일 `skills` 테이블 + lifecycle 컬럼만 있고 3계층 분리는 X.

이 상태로 PR-2(ORM SSOT 통합)를 진행하려 했으나, 책임 경계 자체가 모호해 단순 통합이 불가능하다는 점이 확인됐다.

## Decision

두 모듈을 **책임 단일화** 원칙으로 재정의한다:

### `database/` — 영속화 인프라 (RDB + object storage)

**모든 영속화 인프라**를 담당한다. 도메인 의존 없는 framework-level 계층.

- RDB DDL(`schemas/`) — 기존 유지
- RDB 마이그레이션 도구(`scripts/migrate.py`, `scripts/diagnose.py`, ADR-0011) — 기존 유지
- **ORM 모델(SQLAlchemy)** — 모든 테이블의 SSOT를 여기로 이전
- **Repository 구현체** — 다른 모듈의 Port ABC를 구현 (`PgSessionRepository`, `PgWorkflowRepository` 등)
- **Mapper** — ORM ↔ 도메인 엔티티 변환
- **Object storage 어댑터** — `GCSAdapter`, `ClamAVAdapter`, `LocalStorageAdapter`
- **Object storage 도메인** — `StorageObject`, `UploadPolicy`, `RetentionPolicy`, `ObjectStoragePort`
- `BaseCipher` Protocol(`src/protocols.py`, ADR-0004) — 기존 유지

즉 REQ-008 spec의 §13-62 (object storage + RDB Repository)를 REQ-001로 흡수.

### `modules/storage/` → 향후 명칭은 **`modules/skills_marketplace/`** (이번 ADR 결정 후 rename 권장, 별도 후속 PR)

**Skills Marketplace 도메인 전용**. 3계층 lifecycle(personal → team → company 승격) 책임.

- Domain 엔티티: `PersonalSkill`, `TeamSkill`, `CompanySkill` (3계층) + `SkillLifecycle` 상태머신 + `ApprovalWorkflow` VO
- Application Use Cases: `PublishSkillUseCase` (개인 → 팀 승격), `PromoteToCompanyUseCase` (팀 → 전사 승격), `SearchSkillsUseCase` (하이브리드 검색), `ApproveSkillUseCase`
- Ports: `SkillRepository` (database가 구현), `SkillEmbedderPort` (BGE-M3 호출)
- Workflow Composer가 노드/스킬 후보 검토 시 `SearchSkillsUseCase`를 호출하는 흐름이 주요 downstream.

즉 REQ-008 spec의 §64-72(Marketplace)만 남기고 나머지 모두 REQ-001로 이관.

### `PersonalSkill` 이름 충돌 해소

PR #54(Personalization Agent)의 `ai_agent/domain/entities/personal_skill.py:PersonalSkill`은 사용자 패턴 메모리(Claude Code `memory.md` 차용)로, marketplace의 `PersonalSkill`(워크플로우 스킬 노드)과 도메인이 완전히 다르다. **PR #54 측의 `PersonalSkill`을 rename** 한다 — marketplace 쪽이 "skill" 본연 의미에 더 가까우므로.

후보 (햄햄과 협의 후 확정):
- `UserMemoryArtifact`
- `MemoryPattern`
- `UserPattern`
- `PersonalMemoryEntry`

햄햄 PR #54 fix 시점에 함께 변경하거나, 머지 후 follow-up PR로 처리.

## Consequences

### Positive
- 모듈 책임 단일화 — `database/`는 framework-level 영속화, `modules/storage/`(→`skills_marketplace/`)는 순수 도메인.
- Skills Marketplace 3계층 lifecycle을 spec/코드에 명시적 모델링 가능.
- 두 ORM 정의가 한 곳(database)에 통일되어 schema와 정합성 보장.
- 다른 모듈(`auth`, `ai_agent`, `toolset` 등) Port 구현이 `database/`에서 일관 제공 — composition root 단순화.

### Negative / Trade-offs
- **큰 코드 이전 작업** — 현 `modules/storage/orm/`, `repositories/`, `mappers/`, `adapters/` 대부분을 `database/`로 이전. PR-2부터 PR-2e까지 단계 PR 다수 발생.
- **`modules/storage/` 디렉토리 rename** — 의미를 명확히 하려면 `modules/skills_marketplace/`로 변경 권장. import 경로 전면 변경(`from storage.x` → `from skills_marketplace.x`) — 영향 큰 작업이라 별도 PR.
- **PR #54의 `PersonalSkill` rename** — 햄햄 작업 영향. 협의 필요.
- **REQ-001 / REQ-008 spec 전면 재작성** — 본 ADR과 함께 spec도 동기화.
- **clean_architecture.md §8.1 갱신** — `database/`가 "순수 SQL 계층"이 아님이 됨. infrastructure 계층 본부로 재정의.

### Follow-ups (별도 PR로 분리)

| 단계 | 작업 | 의존 |
|---|---|---|
| **PR-2a** | `database/src/models/` ↔ `modules/storage/orm/` 9개 중복 ORM을 schema와 reconcile + `database/`를 SSOT로 통일 (모듈 rename은 따로) | 본 ADR 머지 |
| **PR-2b** | 중복 8개 Repository 통합 + Mapper 이전 | PR-2a |
| **PR-2c** | `modules/storage/`의 object storage(`StorageObject`, `GCSAdapter`, `ClamAVAdapter`) → `database/`로 이전 | PR-2b |
| **PR-2d** | `modules/storage/` → `modules/skills_marketplace/` rename + 3계층 도메인 신설 (`TeamSkill`, `CompanySkill`, 승격 lifecycle) | PR-2c |
| **PR-2e** | `database/schemas/` 신규 — 3계층 skills 테이블 분리 (`personal_skills`/`team_skills`/`company_skills`) | PR-2d. spec 확정 후 |
| **별도** | PR #54 `PersonalSkill` rename (햄햄 협의) | 본 ADR 머지 후 |

## Alternatives Considered

- **Option A: 현 spec 유지(storage가 잡탕)** — 기각. 책임 모호로 PR-2 통합 작업이 매번 막힘. 새 sub-agent가 어디 모듈에 코드를 둘지 결정 불가.
- **Option B: storage를 더 잘게 쪼개기(`storage_objects`, `storage_repos`, `storage_marketplace` 세 모듈)** — 기각. 모듈 수 늘면 의존 그래프 복잡도 증가. 두 책임 단일화가 더 깔끔.
- **Option C: ORM SSOT만 단발 정리, marketplace는 별도 spec 확정 후** — 기각. PR-2 진행 중 marketplace 의도가 spec과 어긋남이 또 발견될 위험. 한 번에 책임을 박는 게 안전.

## References

- ADR-0011: 마이그레이션 운영성 패턴 (raw SQL + tracking + bootstrap)
- REQ-001 spec: `docs/specs/REQ-001-database.md` (본 ADR로 책임 확장)
- REQ-008 spec: `docs/specs/REQ-008-storage.md` (본 ADR로 marketplace 전용으로 축소)
- clean_architecture.md §8.1 (본 ADR로 갱신)
- PR #61: 마이그레이션 운영성 — 본 ADR의 직전 작업
- PR #54: Personalization Agent — `PersonalSkill` 이름 충돌 발견 계기
