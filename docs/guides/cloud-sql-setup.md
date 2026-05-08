# Cloud SQL 개발 인스턴스 세팅 가이드

## 요구사항 요약

| 항목 | 값 |
|------|-----|
| PostgreSQL 버전 | **16** |
| 필수 확장 | `pgcrypto`, `vector` (pgvector) |
| 테이블 수 | 37+ (15개 SQL 파일) |
| 벡터 차원 | 1024 (BGE-M3) |
| 인덱스 | HNSW (vector_cosine_ops), GIN (FTS) |
| 파티셔닝 | node_logs RANGE (월별) |

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

### 옵션 A: gcloud CLI (추천)

```powershell
gcloud sql instances create workflow-dev --database-version=POSTGRES_16 --tier=db-f1-micro --region=asia-northeast3 --storage-size=10GB --storage-type=HDD --availability-type=zonal --edition=enterprise --root-password=<STRONG_PASSWORD>
```

| 파라미터 | 설명 |
|----------|------|
| `db-f1-micro` | 최소 사양 (vCPU 공유, 614MB RAM), 개발용 충분 |
| `asia-northeast3` | 서울 리전 (레이턴시 최소화) |
| `HDD` | 개발용이라 SSD 불필요, 비용 절감 |
| `--edition=enterprise` | Enterprise 에디션 (db-f1-micro 호환) |

> 생성까지 3-5분 소요. pgvector는 인스턴스 생성 후 `CREATE EXTENSION`으로 활성화

### 옵션 B: GCP 콘솔 (클릭)

1. https://console.cloud.google.com/sql → **인스턴스 만들기** → **PostgreSQL**
2. 인스턴스 ID: `workflow-dev`
3. 비밀번호 설정
4. 데이터베이스 버전: **PostgreSQL 16**
5. Cloud SQL 버전: **Enterprise**
6. 리전: **asia-northeast3 (서울)**
7. 머신 구성: **공유 코어 → db-f1-micro**
8. 스토리지: **HDD, 10GB**
9. **인스턴스 만들기** 클릭

---

## 3단계: 데이터베이스 생성 + 접속 허용

```powershell
# 데이터베이스 생성
gcloud sql databases create workflow_automation --instance=workflow-dev

# 현재 공인 IP 확인
Invoke-RestMethod ifconfig.me

# 내 IP 허용 (개발용, <MY_PUBLIC_IP>를 위 결과로 교체)
gcloud sql instances patch workflow-dev --authorized-networks=<MY_PUBLIC_IP>/32

# 팀원 IP도 추가할 경우 (쉼표 구분)
gcloud sql instances patch workflow-dev --authorized-networks=<IP1>/32,<IP2>/32,<IP3>/32
```

### 접속 정보 확인

```powershell
# 인스턴스 공인 IP 확인
gcloud sql instances describe workflow-dev --format="value(ipAddresses[0].ipAddress)"
```

---

## 4단계: pgvector + pgcrypto 확장 활성화

Cloud SQL에 직접 접속해서 확장을 활성화해야 합니다.

Windows에서 psql이 없으면 **pgAdmin** 또는 **DBeaver**로 접속하세요.

psql이 있는 경우:

```powershell
psql "host=<INSTANCE_IP> port=5432 dbname=workflow_automation user=postgres password=<PASSWORD>"
```

접속 후:

```sql
-- 필수 확장 활성화
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 확인
SELECT * FROM pg_extension WHERE extname IN ('pgcrypto', 'vector');
```

---

## 5단계: 스키마 적용 (PR #8 브랜치)

### 방법 A: 마이그레이션 스크립트 사용

```powershell
# feature/req-001-database 브랜치 체크아웃
git checkout feature/req-001-database

# 환경변수 설정
$env:DATABASE_URL = "postgresql+asyncpg://postgres:<PASSWORD>@<INSTANCE_IP>:5432/workflow_automation"

# 마이그레이션 실행
cd database
pip install -e ".[dev]"
python -m scripts.migrate
```

### 방법 B: SQL 파일 수동 적용 (psql 또는 GUI 툴)

순서대로 실행:

```
001_core.sql                    -- users, departments, workflows, executions
002_credentials_agents_webhooks.sql  -- credential vault, agents, webhooks
003_node_logs_partitioned.sql   -- node_logs (월별 파티션)
004_approval_notifications.sql  -- approvals, notifications
005_skill_bootstrap.sql         -- skills + vector HNSW
006_doc_parser.sql              -- parsed documents
007_langgraph_checkpoints.sql   -- LangGraph checkpoints
008_oauth_security.sql          -- OAuth + security logs
009_node_definitions.sql        -- 54종 노드 정의 + vector
010_intent_feedback.sql         -- intent logs, feedback
011_session_storage.sql         -- chat sessions
012_agent_memory.sql            -- agent memory + vector HNSW
013_marketplace.sql             -- marketplace reviews
014_audit_logs.sql              -- audit trail
015_node_logs_extended.sql      -- node_logs 확장 컬럼
```

### 시드 데이터

```powershell
# 54종 MVP 노드 정의 시드
python -m scripts.seed

# 시스템 유저 시드 (psql)
psql "host=<INSTANCE_IP> port=5432 dbname=workflow_automation user=postgres password=<PASSWORD>" -f seeds/system_user.sql
```

---

## 6단계: 접속 테스트

```python
# 빠른 접속 확인 (Python)
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def test():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:<PASSWORD>@<INSTANCE_IP>:5432/workflow_automation"
    )
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

asyncio.run(test())
```

---

## 7단계: PR #8 테스트 실행

```powershell
git checkout feature/req-001-database
cd database

# DATABASE_URL 환경변수 설정
$env:DATABASE_URL = "postgresql+asyncpg://postgres:<PASSWORD>@<INSTANCE_IP>:5432/workflow_automation"

# 테스트 실행 (주의: conftest.py를 DATABASE_URL 기반으로 수정 필요)
pytest tests/ -v
```

### 테스트 체크리스트

- [ ] 15개 SQL 스키마 적용 성공
- [ ] 54종 node_definitions 시드 적용
- [ ] Vector search: HNSW cosine similarity 쿼리
- [ ] node_logs 파티션 라우팅 (2026_05, 2026_06, 2026_07)
- [ ] CredentialStore encrypt/decrypt round-trip
- [ ] SessionRepository CRUD

---

## 비용 관리

| 항목 | 예상 비용 |
|------|----------|
| db-f1-micro (상시 가동) | ~$7-10/월 |
| 스토리지 10GB HDD | ~$0.90/월 |
| 네트워크 (같은 리전) | 무료 |

### 비용 절감 팁

```powershell
# 개발 안 할 때 인스턴스 중지 (비용 대폭 절감)
gcloud sql instances patch workflow-dev --activation-policy=NEVER

# 다시 시작
gcloud sql instances patch workflow-dev --activation-policy=ALWAYS
```

> **주의**: 중지해도 스토리지 비용은 발생합니다. 완전히 안 쓰면 삭제가 낫습니다.

---

## .env 템플릿

```env
# Database (Cloud SQL)
DATABASE_URL=postgresql+asyncpg://postgres:<PASSWORD>@<INSTANCE_IP>:5432/workflow_automation

# psql 직접 접속용 (동기 드라이버)
DATABASE_URL_SYNC=postgresql://postgres:<PASSWORD>@<INSTANCE_IP>:5432/workflow_automation
```

> `.env`는 `.gitignore`에 포함되어 있으므로 커밋되지 않습니다.

---

## 다음 단계

1. Cloud SQL 인스턴스 생성 + 스키마 적용
2. PR #8 테스트 통과 확인
3. PR #8 머지 → development
4. 팀원에게 접속 정보 공유 (Secret Manager 또는 직접 전달)
5. PR #23 (REQ-008 Storage) 테스트 → 머지
6. REQ-007 실행엔진, REQ-009 API 서버 착수
