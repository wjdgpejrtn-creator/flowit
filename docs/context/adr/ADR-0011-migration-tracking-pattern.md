# ADR-0011: schema_migrations 추적 + bootstrap 기반 raw SQL 마이그레이션

- **Status**: Accepted
- **Date**: 2026-05-14
- **Deciders**: @dhwang0803-glitch (REQ-001)
- **Tags**: area/database, layer/persistence

## Context

REQ-001 Database 모듈은 `database/schemas/*.sql` 16개 파일과 `MigrationRunner`(raw SQL 실행기)로 PostgreSQL 스키마를 관리한다. PR #54(Personalization sub-agent) unblock 진단(2026-05-14, `database/scripts/diagnose.py`)에서 다음 두 약점이 표면화됐다:

1. **추적 부재** — 어느 `.sql` 파일이 staging Cloud SQL에 적용됐는지 기록이 없다. `MigrationRunner.run_schemas()`는 매 실행마다 모든 파일을 무조건 재실행하므로, 이미 적용된 staging에서 두 번째 실행이 즉시 `CREATE TABLE` 충돌로 깨진다.
2. **현재 staging이 묵시적으로 동기화된 상태** — 누가 언제 적용했는지 git/문서/메모리 어디에도 기록 없음. 다음에 신규 `.sql`이 추가되면 안전하게 적용할 도구가 없다.

신규 sub-agent(Skills Builder, Personalization)가 늘어나며 RDB 변경 빈도가 증가할 것이라 단발성 해결이 아닌 운영 패턴 정립이 필요했다.

## Decision

raw SQL 흐름을 유지하면서 다음 4 요소를 도입한다:

1. **`schema_migrations` 추적 테이블** (`database/schemas/000_migration_tracking.sql`) — `filename` PK, `sha256`, `applied_at`, `applied_by`, `bootstrapped` 컬럼. `MigrationRunner`가 lexicographically 첫 번째로 실행해 chicken-and-egg 회피.
2. **Hash 기반 멱등** — 적용된 파일과 hash가 일치하면 SKIP, 다르면 `MigrationError` fail-loud. **schema 파일은 적용 후 immutable** — 변경하려면 새 파일을 추가해야 함.
3. **Bootstrap backfill** — 추적 테이블에 기록은 없는데 그 파일이 declare한 모든 테이블이 이미 존재하면, SQL 실행 없이 `bootstrapped=TRUE`로 마킹. 현재 staging처럼 추적 테이블 도입 전 적용된 환경을 한 번에 흡수한다.
4. **Schema 격리 인자** — `MigrationRunner(schema_name=...)`로 임의의 PostgreSQL schema에 한정 동작. 테스트는 `test_mig_<uuid>` schema에서 실행해 `public`을 보호한다.

**Alembic은 도입하지 않는다.** 현재 raw SQL 흐름이 (a) 16개 파일이 손으로 작성된 상태로 검증돼 있고 (b) 팀 전체가 SQL 직접 작성에 익숙하며 (c) Alembic 도입은 모든 기존 ORM 모델을 autogenerate baseline으로 끌어와야 하는 큰 작업이라, 비용 대비 이득이 명확하지 않다.

## Consequences

### Positive
- `migrate.py` 재실행 안전 (멱등 + skip).
- 신규 `.sql` 추가 시 `migrate.py` 한 번이면 자동 적용.
- 격리된 schema에서 테스트 검증 가능 ([[team_local_env_policy]] 부합 — 로컬 Docker/testcontainers 회피, staging Cloud SQL 공유).
- staging의 묵시적 적용 상태가 backfill로 자동 정리됨.

### Negative / Trade-offs
- schema 파일 immutability — 오타 수정도 별도 마이그레이션으로 처리해야 함. 작은 변경의 PR 비용 증가.
- bootstrap이 declared 테이블만 보고 판정하므로, **테이블이 모두 있지만 인덱스/트리거/제약이 누락된 부분 적용 케이스**는 잘못 backfill될 수 있음. 진단 스크립트(`diagnose.py`)로 보완 필요.
- Alembic 도입을 미뤘으므로 향후 ORM autogenerate가 필요해지면 별도 ADR 필요.

### Follow-ups
- [PR-2] ORM SSOT 통합 — `database/src/models/` ↔ `modules/storage/orm/` 중복 정리 (이 ADR과 독립).
- [향후] CI에서 `migrate.py --status` 자동 실행으로 staging drift 감지.
- staging `schema_migrations` 테이블 적용 + bootstrap 검증은 PR-1 머지 직후 조장이 1회 수행. 결과는 [[staging_db_state]] 갱신.

## Alternatives Considered

- **Option A: Alembic 전면 도입** — 기각. 16개 파일을 baseline migration으로 변환하고 ORM 메타데이터와 동기화하는 작업이 PR-1 스코프를 초과. ORM SSOT(PR-2)가 끝나기 전엔 autogenerate 시 두 모델 트리 충돌 위험.
- **Option B: 추적 테이블 없이 모든 .sql에 IF NOT EXISTS만 보강** — 기각. 멱등은 되지만 "어느 파일이 staging에 들어 있는지" 가시성이 여전히 0. drift 감지 불가.
- **Option C: 각 .sql 파일 상단에 `-- @migration_id=...` 주석으로 자체 추적** — 기각. DDL 파일 안에 메타데이터 주입은 SQL 도구 호환성 저하.

## References

- 진단 결과 스냅샷: 메모리 `staging_db_state.md` (2026-05-14)
- 진단 스크립트: `database/scripts/diagnose.py`
- 구현: `database/schemas/000_migration_tracking.sql`, `database/src/helpers/migration_runner.py`, `database/scripts/migrate.py`
- 테스트: `database/tests/test_migration_runner.py` (5종 시나리오 + schema 식별자 가드)
- PR #54 (Personalization sub-agent) — 본 작업의 unblock 계기
