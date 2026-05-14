# DB 마이그레이션 운영 가이드

REQ-001 Database 모듈의 schema 변경/적용 절차. ADR-0011(`schema_migrations` 추적 + bootstrap)을 따른다.

---

## 0. 사전 지식

- **schema 파일**: `database/schemas/NNN_<name>.sql`. `NNN`은 lexicographically 정렬되는 3자리 숫자(`000`~).
- **추적 테이블**: `schema_migrations`. `MigrationRunner`가 자동 관리. 사람이 직접 INSERT/UPDATE 금지.
- **중요 원칙**: schema 파일은 적용 후 **immutable**. 오타/추가 변경도 새 파일을 만들어야 한다.

---

## 1. 새 schema 변경 절차

### A. 새 파일 추가

```
database/schemas/017_<짧은_설명>.sql
```

- 번호: 마지막 `.sql`보다 1 큰 값.
- 멱등 작성: `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 등. (이후 단계의 backfill/skip이 잘 동작하려면 멱등이 강력 권장.)
- 의존성: 다른 파일의 테이블을 참조하면 그 파일이 더 작은 번호여야 함.

### B. 로컬 검증 (격리 schema)

`database/tests/test_migration_runner.py` 패턴을 따라 임시 schema에서 적용 시뮬레이션:

```powershell
$env:PYTHONUTF8 = "1"
$env:CLOUD_SQL_INSTANCE = "<GCP_PROJECT_ID>:<REGION>:<INSTANCE>"
$env:DB_IAM_USER        = "<본인>@gmail.com"
$env:DB_NAME            = "workflow_automation"

python -m pytest database/tests/test_migration_runner.py -v
```

새로 추가한 .sql만 따로 검증하려면 `MigrationRunner(engine, schemas_dir=tmp_path, schema_name="test_<feature>_<random>")` 패턴으로 ad-hoc 스크립트 작성.

> 격리에는 PostgreSQL `CREATE SCHEMA` 권한이 필요. `cloud-sql-setup.md` §4의 `GRANT CREATE ON DATABASE`가 본인 IAM 계정에 적용돼 있어야 한다.

### C. PR 등록

- 브랜치: `feature/req-XXX-<schema-feature>` 또는 `chore/db-<descrption>`.
- 리뷰 포인트: schema 파일 immutable 원칙 준수, FK/index 일관성, 멱등 작성 여부.

---

## 2. staging 적용

PR 머지 후 staging Cloud SQL에 반영. **IAM 인증이 표준 흐름** (cloud-sql-setup.md §7과 동일 변수):

```powershell
$env:CLOUD_SQL_INSTANCE = "<GCP_PROJECT_ID>:<REGION>:<INSTANCE>"
$env:DB_IAM_USER        = "<본인>@gmail.com"
$env:DB_NAME            = "workflow_automation"
$env:PYTHONUTF8         = "1"
python -m database.scripts.migrate --status   # 예측 표시
python -m database.scripts.migrate            # 실제 적용
```

`DATABASE_URL`도 fallback으로 지원 (legacy / Cloud SQL Auth Proxy 등):

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://user:pwd@host:5432/db"
python -m database.scripts.migrate
```

각 파일별로 출력:
- `[APPLY ]` — 신규 파일, SQL 실행 + 추적 기록.
- `[SKIP  ]` — 이미 적용 + hash 일치, no-op.
- `[BACK  ]` — 추적 기록 없는데 declared 테이블이 이미 존재 → 실행 없이 mark.

---

## 3. 자주 만나는 케이스

### Hash mismatch — 적용된 파일 내용이 변경됨

```
[FAIL] Hash mismatch for 005_skill_bootstrap.sql:
       recorded=a1b2c3d4e5f6…, current=x9y8z7w6v5u4…
```

**원인**: 적용된 파일을 직접 편집(immutable 원칙 위반). 의도적으로 schema를 변경해야 한다면:
1. 파일 변경을 되돌리고
2. **새 마이그레이션 파일**(`017_<change_description>.sql`)을 만들어 `ALTER TABLE` 등으로 차이만 정의
3. 그 새 파일을 PR로 머지

### Bootstrap이 잘못 동작 — 인덱스/트리거가 누락된 부분 적용 케이스

bootstrap은 `CREATE TABLE`로 declare된 **테이블 이름**만 보고 판정한다. 같은 이름의 테이블이 있지만 인덱스/트리거/제약이 누락된 환경에선 잘못 backfill될 수 있음. 이 경우:

1. `database/scripts/diagnose.py`로 인덱스/제약 누락을 별도 점검 (확장 필요 시 후속 PR).
2. 누락분만 보강하는 새 마이그레이션 파일 추가.

### Staging이 깨짐 (`CREATE TABLE` 충돌)

PR-1 머지 전 적용된 staging이라 추적 테이블이 비어 있는 상태. 정상 흐름이라면 첫 `migrate.py` 실행 시 모든 기존 파일이 `[BACK]`으로 처리되어야 함. 만약 `[APPLY]`로 처리되어 충돌하면, 그 파일이 declare한 테이블 일부가 누락된 상태(부분 적용). 누락 테이블을 수동 확인 후 정리.

---

## 4. 진단 스크립트

```powershell
python -m database.scripts.diagnose
```

- staging의 현재 적용 상태(추적 테이블 + 16개 schema 파일별 declared 테이블 존재 여부)를 표 + JSON으로 출력.
- 새 sub-agent 환경 셋업이나 "지금 staging 어떤 상태?" 의문이 들 때 첫 점검 도구.

---

## 5. 권한 체크리스트

| 권한 | 누구에게 | 어디 | 누락 시 에러 |
|---|---|---|---|
| `roles/cloudsql.client` | 모든 팀원 | GCP IAM (project) | 접속 자체 실패 |
| Cloud SQL IAM user 등록 | 모든 팀원 | `gcloud sql users create ... --type=CLOUD_IAM_USER` | 접속 자체 실패 |
| `GRANT ALL PRIVILEGES ON DATABASE` | 모든 팀원 | DB 내부 (postgres superuser로 1회) | 기존 테이블 SELECT 실패 |
| `GRANT CREATE ON DATABASE` | 모든 팀원 | DB 내부 | `permission denied for database` — 테스트 격리 schema 생성 시 |
| `GRANT CREATE ON SCHEMA public` | 모든 팀원 | DB 내부 | `permission denied for schema public` — 마이그레이션 첫 적용 시 |

자세한 설정은 `docs/guides/cloud-sql-setup.md` §4.

---

## 참조

- ADR-0011: `docs/context/adr/ADR-0011-migration-tracking-pattern.md`
- 진단 스크립트: `database/scripts/diagnose.py`
- 마이그레이션 러너: `database/src/helpers/migration_runner.py`
- 테스트: `database/tests/test_migration_runner.py`
- 팀 환경 정책: 메모리 `team_local_env_policy.md`
