# Cloud SQL 개발 인스턴스 세팅 가이드

## 접속 방식: IAM 인증 + Cloud SQL Python Connector

Cloud SQL Proxy나 IP 화이트리스트 없이, **GCP IAM 계정으로 직접 인증**하여 접속한다.
팀원은 `gcloud auth application-default login`만 하면 어디서든 접속 가능.

---

## 요구사항

| 항목 | 값 |
|------|-----|
| PostgreSQL 버전 | **16** |
| 필수 확장 | `pgcrypto`, `vector` (pgvector) |
| 테이블 수 | 37+ (15개 SQL 파일) |
| 벡터 차원 | 1024 (BGE-M3) |
| 인덱스 | HNSW (vector_cosine_ops), GIN (FTS) |
| Python 패키지 | `cloud-sql-python-connector[asyncpg]>=1.12` |

---

## 1단계: GCP 프로젝트 준비

```powershell
# gcloud CLI 설치 확인
gcloud --version

# 로그인 (브라우저 팝업)
gcloud auth login

# 프로젝트 설정 (프로젝트 ID로 교체)
gcloud config set project <YOUR_PROJECT_ID>

# 필요한 API 활성화
gcloud services enable sqladmin.googleapis.com sql-component.googleapis.com
```

> gcloud CLI가 없으면: https://cloud.google.com/sdk/docs/install

---

## 2단계: Cloud SQL 인스턴스 생성

### gcloud CLI

```powershell
gcloud sql instances create workflow-dev `
    --database-version=POSTGRES_16 `
    --tier=db-f1-micro `
    --region=asia-northeast3 `
    --storage-size=10GB `
    --storage-type=HDD `
    --availability-type=zonal `
    --edition=enterprise `
    --database-flags=cloudsql.iam_authentication=on `
    --root-password=<STRONG_PASSWORD>
```

> `--database-flags=cloudsql.iam_authentication=on` — IAM 인증 활성화 필수

### GCP 콘솔

1. https://console.cloud.google.com/sql → **인스턴스 만들기** → **PostgreSQL**
2. 인스턴스 ID: `workflow-dev`
3. 비밀번호 설정
4. 데이터베이스 버전: **PostgreSQL 16**
5. Cloud SQL 버전: **Enterprise**
6. 리전: **asia-northeast3 (서울)**
7. 머신 구성: **공유 코어 → db-f1-micro**
8. 스토리지: **HDD, 10GB**
9. **플래그** 탭 → `cloudsql.iam_authentication` = `on` 추가
10. **인스턴스 만들기** 클릭

---

## 3단계: 데이터베이스 생성

```powershell
gcloud sql databases create workflow_automation --instance=workflow-dev
```

---

## 4단계: IAM 사용자 등록

팀원별 GCP 계정(Gmail)을 Cloud SQL IAM 사용자로 등록한다.

```powershell
# 팀원 IAM 사용자 추가 (각 팀원마다 실행)
gcloud sql users create dhwang0803@gmail.com --instance=workflow-dev --type=CLOUD_IAM_USER
gcloud sql users create <팀원2>@gmail.com --instance=workflow-dev --type=CLOUD_IAM_USER
gcloud sql users create <팀원3>@gmail.com --instance=workflow-dev --type=CLOUD_IAM_USER
gcloud sql users create <팀원4>@gmail.com --instance=workflow-dev --type=CLOUD_IAM_USER
gcloud sql users create <팀원5>@gmail.com --instance=workflow-dev --type=CLOUD_IAM_USER
```

### IAM 역할 부여

팀원에게 Cloud SQL 접속 권한을 부여한다.

```powershell
# 각 팀원에게 Cloud SQL Client 역할 부여
gcloud projects add-iam-policy-binding <YOUR_PROJECT_ID> `
    --member="user:dhwang0803@gmail.com" `
    --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding <YOUR_PROJECT_ID> `
    --member="user:<팀원2>@gmail.com" `
    --role="roles/cloudsql.client"

# ... 나머지 팀원도 동일
```

### DB 내부 권한 부여

IAM 사용자에게 데이터베이스 테이블 접근 권한을 부여한다.
postgres 비밀번호로 접속하여 실행:

```sql
-- 각 IAM 사용자에게 권한 부여 (이메일 전체 사용)
GRANT ALL PRIVILEGES ON DATABASE workflow_automation TO "dhwang0803@gmail.com";
GRANT CREATE ON DATABASE workflow_automation TO "dhwang0803@gmail.com";   -- 신규 schema 생성용 (테스트 격리 등)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "dhwang0803@gmail.com";
GRANT CREATE ON SCHEMA public TO "dhwang0803@gmail.com";                  -- public schema 안에 새 테이블 생성용 (마이그레이션 등)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO "dhwang0803@gmail.com";

-- 나머지 팀원도 동일하게 실행
```

> **PG 16 + Cloud SQL IAM에서 별도로 명시해야 하는 두 GRANT**:
>
> | GRANT | 부여 권한 | 누락 시 에러 |
> |---|---|---|
> | `GRANT CREATE ON DATABASE workflow_automation` | 새 PostgreSQL schema 생성 (`CREATE SCHEMA "test_mig_xxx"`) | `permission denied for database workflow_automation` (테스트 격리에서) |
> | `GRANT CREATE ON SCHEMA public` | public schema 안에 새 테이블/객체 생성 (`CREATE TABLE schema_migrations`) | `permission denied for schema public` (마이그레이션 첫 적용에서) |
>
> PG 15+에서 `public` schema의 CREATE 권한이 PUBLIC role에서 박탈된 게 후자의 원인.
> `ALL PRIVILEGES ON ALL TABLES`은 기존 테이블 read/write만 부여 — 새 테이블 생성은 별개.

검증:

```sql
SELECT
    has_database_privilege('<email>@gmail.com', 'workflow_automation', 'CREATE') AS db_create,
    has_schema_privilege('<email>@gmail.com', 'public', 'CREATE') AS schema_create;
-- 둘 다 t (true)가 나와야 함
```

> **DB context 주의**: `GRANT ON SCHEMA public`은 **DB-scoped**. SQL Studio에서 GRANT 실행 시 상단 DB selector가 `workflow_automation`인지 먼저 확인. 다른 DB(`postgres` 등)에 적용하면 효력 없음. 현재 DB는 `SELECT current_database();`로 검증.

### 4-1. 공유 ownership role — `workflow_admin`

`GRANT`만으로는 SELECT/INSERT/UPDATE/DELETE는 가능하지만 **`ALTER TABLE`(스키마 변경)은 테이블 owner만 가능**. 마이그레이션 파일이 ALTER를 포함하면 IAM 사용자는 `must be owner of table ...`로 막힌다. 팀 전체가 ALTER 가능하게 하려면 **공유 role을 owner로 두고 모든 IAM 사용자를 그 role의 멤버**로 등록한다.

postgres superuser로 1회 실행 (`gcloud sql connect workflow-dev --user=postgres --database=workflow_automation`):

```sql
-- 1. 공유 role 생성 + 팀원 멤버십
CREATE ROLE workflow_admin NOLOGIN;
GRANT workflow_admin TO "dhwang0803@gmail.com";
GRANT workflow_admin TO "<팀원2>@gmail.com";
-- ... 모든 팀원

-- 2. 기존 모든 테이블 ownership을 workflow_admin으로 이전
DO $$
DECLARE tbl text;
BEGIN
    FOR tbl IN SELECT tablename FROM pg_tables WHERE schemaname='public'
    LOOP
        EXECUTE format('ALTER TABLE public.%I OWNER TO workflow_admin', tbl);
    END LOOP;
END $$;

-- 3. workflow_admin 자체에 schema/db 권한
GRANT CREATE ON DATABASE workflow_automation TO workflow_admin;
GRANT CREATE, USAGE ON SCHEMA public TO workflow_admin;
```

검증:

```sql
SELECT tablename, tableowner FROM pg_tables WHERE schemaname='public' LIMIT 5;
-- tableowner가 모두 workflow_admin 이어야
```

PG 16 기본 INHERIT 모드라 IAM 사용자가 `workflow_admin` 멤버이면 자동으로 ALTER 권한 상속. `SET ROLE` 명시 불필요.

> **새 팀원 합류 시**: superuser psql에서 `GRANT workflow_admin TO "<email>@gmail.com";` 한 줄.
> **새 테이블이 IAM 사용자 직접 생성 시 owner는 본인 IAM**이 됨. 다른 팀원도 ALTER 가능하게 하려면 추가 `ALTER TABLE x OWNER TO workflow_admin` 필요. 마이그레이션을 통해 만든 테이블은 자동 처리하는 follow-up이 ADR-0011에 적힘.

---

## 5단계: 확장 활성화

postgres 비밀번호로 접속하여 실행:

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 확인
SELECT * FROM pg_extension WHERE extname IN ('pgcrypto', 'vector');
```

---

## 6단계: 스키마 적용

### 방법 A: 스크립트 사용

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://postgres:<PASSWORD>@<INSTANCE_IP>:5432/workflow_automation"

cd database
pip install -e ".[dev]"
python -m scripts.migrate
```

### 방법 B: SQL 파일 수동 적용

순서대로 실행:

```
001_core.sql → 015_node_logs_extended.sql (15개)
```

---

## 7단계: 팀원 로컬 환경 설정

### 한 번만 하면 되는 것

```powershell
# 1. ADC(Application Default Credentials) 로그인
gcloud auth application-default login

# 2. Python 패키지 설치
cd modules/storage
pip install -e ".[dev]"
```

### .env 설정

```env
# Cloud SQL IAM 인증 (필수 3개)
CLOUD_SQL_INSTANCE=<PROJECT_ID>:asia-northeast3:workflow-dev
DB_IAM_USER=<본인이메일>@gmail.com
DB_NAME=workflow_automation
```

> `CLOUD_SQL_INSTANCE`가 설정되면 IAM 인증 모드로 작동.
> 설정 안 하면 기존 `DB_HOST`/`DB_PASSWORD` 방식(로컬 Docker 등)으로 폴백.

### 인스턴스 연결 이름 확인

```powershell
gcloud sql instances describe workflow-dev --format="value(connectionName)"
# 출력: <PROJECT_ID>:asia-northeast3:workflow-dev
```

---

## 8단계: 접속 테스트

```python
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from google.cloud.sql.connector import Connector


async def test():
    connector = Connector()

    async def getconn():
        return await connector.connect_async(
            "<PROJECT_ID>:asia-northeast3:workflow-dev",
            "asyncpg",
            user="<본인이메일>@gmail.com",
            db="workflow_automation",
            enable_iam_auth=True,
        )

    engine = create_async_engine("postgresql+asyncpg://", async_creator=getconn)

    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT version()"))
        print(result.scalar())

        result = await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
        print(f"pgvector: {result.scalar()}")

        result = await conn.execute(text(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
        ))
        print(f"Tables: {result.scalar()}")

    await engine.dispose()
    await connector.close_async()
```

### async vs sync 컴포넌트 — connector 선택

| 실행 모델 | Connector | driver | engine |
|-----------|-----------|--------|--------|
| async (FastAPI api_server, Modal sub-agent) | `create_async_connector()` + `connect_async()` | `asyncpg` | `create_async_engine(..., async_creator=)` |
| **sync** (Celery worker — execution_engine) | `Connector()` + `connect()` | `pg8000` (순수 Python, psycopg2 컴파일 의존성 회피) | `create_engine(..., creator=)` |

Celery worker는 sync 실행 모델이므로 `asyncpg`/`create_async_engine`을 쓸 수 없다. sync
`Connector` + `pg8000` driver를 사용한다 (REQ-007 `execution_engine/dependencies/container.py`).

```python
# sync worker 패턴
from google.cloud.sql.connector import Connector, IPTypes
from sqlalchemy import create_engine

connector = Connector()

def getconn():
    return connector.connect(
        "<PROJECT_ID>:asia-northeast3:workflow-dev",
        "pg8000",
        user="<SA 또는 이메일>",
        db="workflow_automation",
        enable_iam_auth=True,
        ip_type=IPTypes.PUBLIC,  # workflow-dev는 public IP만 — private IP 없음
    )

engine = create_engine("postgresql+pg8000://", creator=getconn, pool_pre_ping=True)


asyncio.run(test())
```

---

## 비용 관리

| 항목 | 예상 비용 |
|------|----------|
| db-f1-micro (상시 가동) | ~$7-10/월 |
| 스토리지 10GB HDD | ~$0.90/월 |
| 네트워크 (같은 리전) | 무료 |

```powershell
# 개발 안 할 때 인스턴스 중지
gcloud sql instances patch workflow-dev --activation-policy=NEVER

# 다시 시작
gcloud sql instances patch workflow-dev --activation-policy=ALWAYS
```

---

## 연결 모드 비교

| 환경 | 환경변수 | 연결 방식 |
|------|---------|----------|
| 팀 개발 (Cloud SQL) | `CLOUD_SQL_INSTANCE` + `DB_IAM_USER` + `DB_NAME` | IAM Python Connector |
| 로컬 Docker | `DB_HOST` + `DB_USER` + `DB_PASSWORD` + `DB_NAME` | 직접 TCP 접속 |
| CI/CD (Cloud Run) | `CLOUD_SQL_INSTANCE` + `DB_IAM_USER` + `DB_NAME` | IAM (서비스 계정) |

> `session_factory.py`가 `CLOUD_SQL_INSTANCE` 유무로 자동 분기한다.

---

## 트러블슈팅

### "PERMISSION_DENIED" 에러

```powershell
# ADC 갱신
gcloud auth application-default login

# Cloud SQL Client 역할 확인
gcloud projects get-iam-policy <PROJECT_ID> --filter="bindings.members:user:<이메일>"
```

### "Could not connect" 에러

```powershell
# 인스턴스 상태 확인
gcloud sql instances describe workflow-dev --format="value(state)"

# 인스턴스가 STOPPED이면 시작
gcloud sql instances patch workflow-dev --activation-policy=ALWAYS
```

### ADC 토큰 만료

`gcloud auth application-default login`을 다시 실행하면 갱신된다.
Python Connector가 토큰 자동 갱신하므로, 서버 프로세스에서는 걱정 불필요.
