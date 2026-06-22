# ADR-0012: `database/` / `modules/storage/` / `modules/skills_marketplace/` 책임 분배

- **Status**: Accepted
- **Date**: 2026-05-14
- **Deciders**: @dhwang0803-glitch (REQ-001 / 조장)
- **Tags**: area/architecture, area/database, area/storage, area/marketplace, layer/infrastructure, layer/domain

## Revision History

- **v1 (2026-05-14, PR #62)**: 초안 — `database/`가 ORM/Repository/object storage를 흡수, `modules/storage/`는 Skills Marketplace 전용으로 축소. PR-2a 사전 점검에서 cross-module import 변경 + CLAUDE.md 5지점 수정 + PR #54 영향이 이득 대비 큰 것으로 판명되어 v2로 재작성.
- **v2 (2026-05-14, PR #63)**: `database/`는 SQL only(원래 의도 복원), `modules/storage/`는 영속화 인프라 그대로 유지, `modules/skills_marketplace/` 신규 모듈로 도메인 분리. import 경로 변경 0건 + PR #54 무영향.
- **v3 (2026-05-14, 본 PR)**: 현재 — PR-2a 작업 중 9쌍 Repository 일괄 분석에서 `database/src/repositories/`(BaseRepository CRUD 패턴, admin/batch/seed 용도)와 `modules/storage/repositories/`(Port-Adapter 패턴, sub-agent 도메인 호출)가 **의도적으로 다른 책임을 가진 두 패턴**임이 확인됨. v2의 follow-up 표 PR-2b/c "중복 통합/이전" 항목은 잘못된 가정이라 폐기. 두 패턴 공존 명시.

> 한나절 내 v1 → v2 재작성 결정은 ADR 위계 약화 우려가 있으나, 외부 referer가 모두 본 PR에서 어차피 갱신되는 시점이라 supersede 별 ADR 분리 대신 본문 갱신으로 정리. 변경 이력은 본 섹션 + git log/blame 으로 보존.

## Context

REQ-001(database) / REQ-008(storage) 두 spec의 책임 경계가 코드 진척 과정에서 흐려졌다. ADR-0011(PR #61) 머지 직후 인벤토리에서 다음이 확인됐다:

1. **REQ-008(storage) spec이 잡탕 구조** — `StorageObject` 도메인 + `GCSAdapter`/`ClamAVAdapter` object storage 어댑터(§13-46) + 다른 모듈 Port 구현체(`PgSessionRepository`, `PgWorkflowRepository` 등 §48-62) + Marketplace 하위 도메인(§64-72) 세 책임이 한 모듈에 묶여 있다.
2. **REQ-001(database) spec은 "순수 SQL 계층"으로 제한**(`docs/context/clean_architecture.md §8.1` "Python 코드 의존 없음")으로 정의됐지만 현실은 `database/src/models/` (27 ORM) + `database/src/repositories/` (19 Repository) + `database/src/helpers/` (CipherProtocol·SessionManager·CredentialStore)가 들어가 있다.
3. **ORM이 두 군데에서 서로 다른 정의로 중복** — 같은 테이블(`workflows`, `agent_memories` 등)에 대해 `database/src/models/`와 `modules/storage/orm/`가 컬럼/FK/인덱스가 다른 모델을 각각 정의. 일부(`modules/storage/orm/workflow_model.py`)는 실제 schema와도 어긋남 (`user_id` 컬럼 누락).
4. **PR #54(Personalization)의 `PersonalSkill` 엔티티가 Marketplace 컨텍스트의 `personal_skills`와 이름 충돌** — 전자는 사용자 패턴/기억(`memory.md` 본문), 후자는 워크플로우 자동화 스킬 노드. 도메인 의미 완전 다름.
5. **Skills Marketplace의 3계층 lifecycle**(personal → team → company 승격)은 spec 합의 당시 구체화되지 않아 현행 schema(`005_skill_bootstrap.sql` + `013_marketplace.sql`)에 단일 `skills` 테이블 + lifecycle 컬럼만 있고 3계층 분리는 X.

## Decision

세 모듈의 **책임 단일화** 원칙으로 정리:

| 모듈 | 책임 | 비고 |
|---|---|---|
| **`database/`** | **순수 SQL 계층** — DDL(`schemas/`), 마이그레이션 도구(`migrate.py`, `diagnose.py`, ADR-0011), seeds, SQL 테스트. **Python ORM/Repository 코드 없음**. | `clean_architecture.md §8.1` 원래 의도 |
| **`modules/storage/`** | **영속화 인프라** — RDB ORM/Repository/Mapper + object storage(GCS, ClamAV) adapter + 자체 도메인(`StorageObject`, `UploadPolicy` 등). CLAUDE.md의 기존 "ORM 본부" 가정 그대로 | 변경 없음 |
| **`modules/skills_marketplace/`** (신규) | **Skills Marketplace 도메인** — `PersonalSkill`/`TeamSkill`/`CompanySkill` 3계층 entity + 승격 lifecycle(`PromoteToTeamUseCase`/`PromoteToCompanyUseCase`) + 하이브리드 검색. Workflow Composer가 노드/스킬 후보 검토 시 호출 | 신규 모듈 (REQ-013 후보) |

### PR #54 `PersonalSkill` 이름 충돌 해소

PR #54(`ai_agent.PersonalSkill`)는 그대로 유지하고 **`skills_marketplace` 측이 다른 이름 채택**한다. 이유:
- PR #54는 이미 OPEN + 햄햄 작업 중. 외부 영향 없는 쪽이 더 적합.
- `skills_marketplace`는 신규 모듈이라 이름 결정 자유도 높음.
- 구체 이름은 `skills_marketplace` 구현 시점(PR-2d)에 옵션 제시 후 결정.

### database/src/* 와 modules/storage/repositories/ 처리 (v3 갱신)

**`database/src/repositories/`와 `modules/storage/repositories/`는 의도된 두 패턴 공존**으로 인정:

| 모듈 | 패턴 | 책임 | 호출자 |
|---|---|---|---|
| `database/src/repositories/` | **BaseRepository CRUD 편의** | ORM 직접 입출력, 자체 클래스 (ABC 무관), `upsert`/`list_by_*` 등 일반 CRUD + 도메인별 특수 메서드 | admin / batch / seed 스크립트 |
| `modules/storage/repositories/` | **Port-Adapter** | 도메인 entity 입출력, 다른 모듈의 ABC(`auth/ai_agent/nodes_graph/toolset`)를 구현 | sub-agent / use case / composition root |

9쌍 Repository 일괄 분석(2026-05-14, PR-2a 작업 중)에서 메서드 시그니처/입출력 타입/사용 컨텍스트가 다름이 확인됨. 같은 테이블을 다루지만 인터페이스가 다른 두 책임이라 단순 통합 부적합.

ORM(`database/src/models/`와 `modules/storage/orm/`)도 두 패턴이 각각 자기 Base에 등록되어 별도 SQLAlchemy 객체. 같은 테이블을 다루지만 충돌 없이 공존 가능 (다른 metadata).

follow-up (v3 정리):

| 단계 | 작업 | 의존 |
|---|---|---|
| **PR-2a** ✓ | `modules/storage/orm/` 9개 ORM을 staging schema와 1:1 정합화 + 도메인 entity와 속성명 일치(`mapped_column("db_col", ...)`로 분리) + Phase 2 mapper/repo fix. **머지 완료 (PR #64, 2026-05-14)** | — |
| ~~PR-2b: 중복 Repository 통합~~ | **폐기** — 두 패턴 의도된 책임 공존 | — |
| ~~PR-2c: database/src 통째 이전~~ | **폐기** — 두 패턴 의도된 책임 공존 | — |
| **PR-2a-3** (재배치) | `WorkflowSchema`/`ExecutionResult` `user_id` 누락 fix + 16+ 사용처 + `execution_mapper`/`skill_mapper` 임시 dataclass → 정식 entity import. PR #64 known issue #1 + #3 해소 | 본 ADR 머지 |
| **PR-2a-4** (재배치) | `services/execution_engine/src/adapters/postgres_*_repo.py` 검증 — 3중 중복으로 의심됐으나 두 패턴 공존 가정 하에 재분석 필요 | PR-2a-3 |
| **PR-2d** | `modules/skills_marketplace/` 신규 모듈 + 3계층 도메인 entity/use cases + `skills_marketplace.PersonalSkill` 이름 옵션 결정 + Skill 관련 코드 `modules/storage`에서 분리 | PR-2a-3 |
| **PR-2e** | 3계층 schema 마이그레이션 (`personal_skills`/`team_skills`/`company_skills` 테이블 분리) + ORM/Repository 추가 | PR-2d, spec 확정 후 |

## Consequences

### Positive
- **CLAUDE.md 거의 그대로 유지** — `storage`가 ORM 본부라는 기존 가정 정확. `skills_marketplace` 신규 등록만.
- **import 경로 변경 0** — `from storage.repositories.x` 그대로. PR #54 sub-agent main.py 영향 없음.
- **database/src/* 폐기 방향 명확** — modules/storage가 SSOT (이미 사실상 그런 구조).
- **모듈 단일 책임 보전** — database=SQL, storage=영속화 인프라, skills_marketplace=도메인. 각 책임 명확.
- **PR #54 무영향** — `ai_agent.PersonalSkill` 그대로 유지. 햄햄 작업 흐름 보전.

### Negative / Trade-offs
- **storage가 약간 "잡탕" 유지** — RDB Repo + object storage adapter + 자체 도메인. "영속화 인프라" 단일 책임으로 묶이긴 하나 도메인 객체(StorageObject) + 인프라 Adapter가 한 모듈에 공존.
- **skills_marketplace REQ 번호 미정** — REQ-008에 sub-domain으로 두거나 REQ-013 신설. 본 ADR은 모듈 위치만 결정, spec 번호는 PR-2d 시점에 결정.
- **본 ADR 한나절 내 v1 → v2 → v3 갱신** — Revision History 섹션으로 변경 이력 보존.
- **ORM/Repository 두 패턴 공존** (v3) — 같은 테이블을 다루는 두 SQLAlchemy 정의가 각자 Base에 register됨. SQLAlchemy 입장에선 충돌 없으나, 신규 작성자는 `database/src/`(BaseRepository 편의) vs `modules/storage/`(Port-Adapter) 어느 쪽에 코드를 둘지 가이드 필요. CLAUDE.md/clean_architecture.md에 책임 명시 추가 권장 (별도 docs PR).

### Follow-ups
- 본 ADR과 동일 PR: REQ-001/REQ-008 spec 헤더 갱신, clean_architecture.md §8.1 갱신, CLAUDE.md skills_marketplace 등록.
- PR-2a~e: 위 follow-up 표.
- 별도: `skills_marketplace.PersonalSkill` 이름 옵션 제시 + 결정 (PR-2d 시점).

## Alternatives Considered

- **v1 안 (database가 ORM 흡수)** — 본 ADR Revision History 참조. cross-module import 경로 변경, CLAUDE.md 5지점 수정, PR #54 영향 등 비용 대비 이득 작아 v2로 재작성.
- **storage를 더 잘게 쪼개기(`storage_objects`, `storage_repos`, `storage_marketplace` 셋)** — 기각. 모듈 수 증가로 의존 그래프 복잡도. 본 ADR의 3 모듈이 균형 잡힘.
- **skills_marketplace를 storage 안의 sub-package로** — 기각. domain 모듈과 infrastructure 모듈을 한 패키지에 두면 의존 방향 추적 어려움. CLAUDE.md "modules/*는 모두 도메인 모듈" 원칙과 일치하려면 별도 modules 패키지.

## References

- ADR-0011: 마이그레이션 운영성 (raw SQL + 추적 + bootstrap) — 본 ADR과 무관, database/scripts/ 운영 패턴
- REQ-001 spec: `docs/specs/REQ-001-database.md`
- REQ-008 spec: `docs/specs/REQ-008-storage.md`
- clean_architecture.md §8.1
- CLAUDE.md
- PR #54 (Personalization Agent): `ai_agent.PersonalSkill` 영향 없음 — 본 ADR 결정으로 보전
- PR #62: 본 ADR v1 머지
- PR #63: 본 ADR v2 갱신 (force push)
- PR #64: PR-2a 머지 (Phase 1 ORM 정합 + Phase 2 mapper/repo fix). PR-2a 작업 중 9쌍 Repository 일괄 분석 결과로 v3 갱신 트리거.
