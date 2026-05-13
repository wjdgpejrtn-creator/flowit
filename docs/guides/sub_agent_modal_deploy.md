# Sub-agent Modal 배포 — 셀프 서비스 가이드

Sprint 3 멀티 에이전트 구조에서 각 sub-agent(Skills Builder / Personalization / 그 외 후속)는 **별도 Modal app**으로 배포되고, staging Cloud SQL에 **IAM 인증**으로 접근한다. 본 가이드는 sub-agent 담당자가 막힘없이 배포까지 갈 수 있게 구성됐다.

> 사전 전제: `docs/guides/cloud-sql-setup.md` (IAM 인증 표준), `services/agents/llm-base/main.py` (참조 구현).

---

## 0. 사전 점검 — 5분

| 항목 | 확인 방법 | 관련 |
|------|----------|------|
| Modal CLI + 공용 토큰 영속화 | `modal profile list` 출력에 `dhwang0803` 워크스페이스 1개 | 전체 |
| `cloudsql-iam-sa` Secret 존재 | `modal secret list` 출력에 포함 | 전체 |
| `llm-base` app 배포됨 | `modal app list`에 `llm-base` state=deployed | 전체 |
| GCP `cloudsql-iam-modal` SA가 DB IAM user로 등록됨 | 조장에게 확인 | 전체 |
| GCS 버킷 + SA storage 권한 | `gcloud storage buckets list --project=<GCP_PROJECT_ID>`에 `<GCS_BUCKET_DEV>` 포함 | Personalization만 |

위 4~5개 중 하나라도 빠지면 조장(황대원)에게 알려야 한다 — **§1은 조장만 1회 실행**한다.

---

## 1. (조장 전용 — 1회) 공용 GCP SA + Modal Secret 등록

Sprint 3 시작 시 한 번만 실행한다. sub-agent가 추가될 때마다 반복하지 않는다.

### 1.1 GCP service account 생성 + 권한

```powershell
$PROJECT  = "<GCP_PROJECT_ID>"
$SA_NAME  = "cloudsql-iam-modal"
$SA_EMAIL = "$SA_NAME@$PROJECT.iam.gserviceaccount.com"

# Service account 생성
gcloud iam service-accounts create $SA_NAME `
  --display-name="Modal workers - Cloud SQL IAM auth" `
  --project=$PROJECT

# Cloud SQL 접속 권한 부여
gcloud projects add-iam-policy-binding $PROJECT `
  --member="serviceAccount:$SA_EMAIL" `
  --role="roles/cloudsql.client"
gcloud projects add-iam-policy-binding $PROJECT `
  --member="serviceAccount:$SA_EMAIL" `
  --role="roles/cloudsql.instanceUser"

# Cloud SQL 인스턴스에 IAM SA user로 등록
gcloud sql users create $SA_EMAIL `
  --instance=workflow-dev `
  --type=CLOUD_IAM_SERVICE_ACCOUNT `
  --project=$PROJECT
```

### 1.2 DB 내부 GRANT (postgres root 비밀번호 필요)

Cloud SQL Auth Proxy 또는 콘솔의 Cloud SQL Studio에서 `postgres` user로 접속해 실행한다. SA 이메일의 `.gserviceaccount.com` 부분은 **제외**하고 GRANT 대상에 사용한다.

```sql
GRANT ALL PRIVILEGES ON DATABASE workflow_automation
  TO "cloudsql-iam-modal@<GCP_PROJECT_ID>.iam";

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public
  TO "cloudsql-iam-modal@<GCP_PROJECT_ID>.iam";

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL PRIVILEGES ON TABLES
  TO "cloudsql-iam-modal@<GCP_PROJECT_ID>.iam";
```

### 1.3 JSON key → Modal Secret 등록

```powershell
# JSON key 발급 (디스크에 잠깐만 남기고 즉시 삭제)
gcloud iam service-accounts keys create modal-sa-key.json `
  --iam-account=$SA_EMAIL `
  --project=$PROJECT

# Modal Secret으로 등록
$saJson = Get-Content modal-sa-key.json -Raw
modal secret create cloudsql-iam-sa GOOGLE_APPLICATION_CREDENTIALS_JSON=$saJson --force

# 디스크에 남기지 않음
Remove-Item modal-sa-key.json
```

확인:
```powershell
modal secret list | Select-String cloudsql-iam-sa
```

### 1.4 (Personalization sub-agent용) GCS 버킷 + SA 권한

Personalization Agent(햄햄)는 사용자별 `MEMORY.md` + frontmatter 파일을 GCS에 저장한다(REQ-004 §6, Claude Code memory.md 패턴 차용). 다른 sub-agent에는 불필요한 단계 — Personalization 들어오는 시점에만 1회 실행.

```powershell
$BUCKET = "<GCS_BUCKET_DEV>"

# 1) dev 버킷 생성 (asia-northeast3, uniform IAM)
gcloud storage buckets create gs://$BUCKET `
  --project=$PROJECT `
  --location=asia-northeast3 `
  --uniform-bucket-level-access

# 2) 공용 SA에 이 버킷에 대해서만 objectAdmin 부여 (최소 권한)
gcloud storage buckets add-iam-policy-binding gs://$BUCKET `
  --member="serviceAccount:$SA_EMAIL" `
  --role="roles/storage.objectAdmin"
```

> 프로젝트 레벨 `roles/storage.objectAdmin`은 부여하지 않는다 — 다른 버킷까지 권한이 새는 걸 막기 위해 버킷 단위 binding을 쓴다.

확인:
```powershell
gcloud storage buckets describe gs://$BUCKET --format="value(name,location)"
gcloud storage buckets get-iam-policy gs://$BUCKET --format="json(bindings[].role,bindings[].members)"
# → roles/storage.objectAdmin + serviceAccount:cloudsql-iam-modal@... 한 줄 있어야 정상
```

---

## 2. (sub-agent 담당자) Modal Secret 등록

본인 sub-agent용 Secret(`agent-<name>-secret`)만 만든다. `cloudsql-iam-sa`는 조장이 이미 등록함.

### 2.1 `.env` 채우기

`.env.example`을 `.env`로 복사 후 아래 5키를 채운다 (`agent-skills-builder-secret` 예시):

```env
LLM_BASE_URL=https://<WORKSPACE>--llm-base.modal.run
EMBEDDING_BASE_URL=https://<WORKSPACE>--llm-base.modal.run
CLOUD_SQL_INSTANCE=<GCP_PROJECT_ID>:<REGION>:<INSTANCE>
DB_IAM_USER=<MODAL_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com
DB_NAME=workflow_automation
```

> `LLM_BASE_URL`은 헬스체크용 (실제 generate는 RPC). `EMBEDDING_BASE_URL`은 BGE-M3 ASGI 호출용 — 동일 URL.
> `DB_IAM_USER`는 **공용 SA의 풀 이메일**(`.gserviceaccount.com` 포함). DB GRANT 시점에는 `.gserviceaccount.com`을 제외하지만 connector는 풀 이메일을 요구한다.

**Personalization sub-agent**는 위 5키에 더해 `GCS_PERSONAL_BUCKET=<GCS_BUCKET_DEV>` 한 줄을 추가한다 — `agent-personalization-secret`에 같이 묶임. `.env.example` 참조.

### 2.2 본인 Secret만 sync

```powershell
python scripts/sync_modal_secrets.py agent-skills-builder-secret
```

`scripts/sync_modal_secrets.py`의 `SECRET_MAPPINGS`에 본인 sub-agent 이름이 없으면 거기 먼저 한 줄 추가한 뒤 실행한다.

---

## 3. (sub-agent 담당자) Modal app 코드 — IAM connector 패턴

`services/agents/agent-<name>/main.py` 골격. `cloud-sql-python-connector`로 IAM 인증을 처리한다.

### 3.1 image 의존성

```python
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi>=0.115",
        "httpx>=0.27",
        "pydantic>=2.13",
        "sqlalchemy[asyncio]>=2.0",
        "asyncpg>=0.30",
        "pgvector>=0.3",
        # Cloud SQL IAM 인증 — google-cloud-sql-connector 만이 enable_iam_auth=True 지원
        "cloud-sql-python-connector[asyncpg]>=1.12",
    )
    # ... add_local_dir / env ...
)
```

### 3.2 Secret 마운트 + boot()

```python
app_secret = modal.Secret.from_name("agent-skills-builder-secret")
gcp_secret = modal.Secret.from_name("cloudsql-iam-sa")

app = modal.App("agent-skills-builder")


@app.cls(
    image=image,
    secrets=[app_secret, gcp_secret],
    timeout=600,
    scaledown_window=300,
)
@modal.concurrent(max_inputs=8)
class SkillsBuilderAgent:

    @modal.enter()
    def boot(self) -> None:
        import json
        import os
        import tempfile
        from pathlib import Path

        from google.cloud.sql.connector import Connector, IPTypes
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        # 1) GCP SA JSON을 임시 파일로 풀고 ADC 변수 지정
        #    google-auth는 GOOGLE_APPLICATION_CREDENTIALS가 가리키는 파일을 읽음
        sa_payload = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
        sa_path = Path(tempfile.gettempdir()) / "gcp-sa.json"
        sa_path.write_text(sa_payload, encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa_path)

        # 2) Cloud SQL Python Connector — IAM 인증 (비밀번호 없음)
        self._connector = Connector()

        async def getconn():
            return await self._connector.connect_async(
                os.environ["CLOUD_SQL_INSTANCE"],
                "asyncpg",
                user=os.environ["DB_IAM_USER"],
                db=os.environ["DB_NAME"],
                enable_iam_auth=True,
                ip_type=IPTypes.PUBLIC,
            )

        self._engine = create_async_engine(
            "postgresql+asyncpg://",
            async_creator=getconn,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        # 3) 어댑터 wiring (RPC LLM + HTTP embedding)
        from ai_agent.adapters.llm.modal_llm_adapter import ModalLLMAdapter
        from ai_agent.adapters.llm.modal_embedding_adapter import ModalEmbeddingAdapter
        self._llm = ModalLLMAdapter()
        self._embedder = ModalEmbeddingAdapter()

    @modal.exit()
    def shutdown(self) -> None:
        import asyncio

        if getattr(self, "_engine", None):
            asyncio.run(self._engine.dispose())
        if getattr(self, "_connector", None):
            asyncio.run(self._connector.close_async())
```

> **금지 패턴**: `os.environ["DATABASE_URL"]`로 DSN 만들기. `DB_PASSWORD` 같은 키 도입. 둘 다 팀 표준(IAM 인증)을 깬다.

### 3.3 헬스체크

`/v1/health`에서 DB 핑을 같이 돌려 503 분기를 시킨다.

```python
@api.get("/v1/health")
async def health() -> dict[str, object]:
    from sqlalchemy import text
    try:
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
        db_err = None
    except Exception as exc:
        db_ok = False
        db_err = repr(exc)

    if not db_ok:
        raise HTTPException(status_code=503, detail={"db": {"ok": False, "error": db_err}})
    return {"status": "ok", "db": "iam-connected"}
```

---

## 4. 배포 + 검증

```powershell
# 1) 배포 — Windows에서는 PYTHONUTF8=1 필수 (Dockerfile cp949 함정)
$env:PYTHONUTF8 = "1"
modal deploy services/agents/agent-skills-builder/main.py

# 2) 배포 후 stdout 끝부분에 endpoint URL이 찍힌다 — LLM_BASE_URL 패턴 검증용
#    https://dhwang0803--agent-skills-builder-skillsbuilderagent-... .modal.run

# 3) 헬스체크 (db: "iam-connected" 또는 503 응답)
curl https://<WORKSPACE>--skills-builder.modal.run/v1/health
```

---

## 5. 흔한 함정

| 증상 | 원인 | 해결 |
|------|------|------|
| `KeyError: 'DATABASE_URL'` | 옛 DSN 패턴 코드 잔재 | §3.2처럼 IAM connector 패턴으로 갈아엎기 |
| `PERMISSION_DENIED: cloud sql admin api` | SA에 `roles/cloudsql.client` 미부여 | §1.1 권한 부여 명령 재실행 |
| `pg_hba.conf rejects connection` | 인스턴스가 IAM auth 플래그 비활성 | `cloudsql.iam_authentication=on` 플래그 확인 |
| `permission denied for table ...` | DB GRANT 누락 | §1.2 GRANT 재실행 — SA 이메일에서 `.gserviceaccount.com` 제외 |
| `Connector lookup not found` | `DB_IAM_USER`에 풀 이메일 누락 | `.gserviceaccount.com` **포함**된 이메일로 (DB user 이름과 다름 — connector는 GCP IAM 식별자 사용) |
| `ENOENT: gcp-sa.json` | `GOOGLE_APPLICATION_CREDENTIALS_JSON` 누락 | `secrets=[..., gcp_secret]` 마운트 확인 |
| Modal cold start 시 SQLAlchemy 첫 호출이 30~60s | Connector OAuth 토큰 교환 + asyncpg TLS handshake | 정상. `pool_pre_ping=True` + scaledown_window로 완화 |
| `cloud-sql-python-connector` import 시 `protobuf` 충돌 | 다른 google-* 라이브러리와 버전 불일치 | image에 `protobuf>=4.25` 명시 핀 또는 `--no-deps` 우회 |
| (Personalization) `403 Forbidden: ... does not have storage.objects.create` | 버킷 IAM에 SA `roles/storage.objectAdmin` 미부여 | §1.4의 `gcloud storage buckets add-iam-policy-binding` 재실행 |
| (Personalization) `NotFound: 404 The specified bucket does not exist` | `GCS_PERSONAL_BUCKET` 값이 dev 버킷 이름과 불일치 | `gcloud storage buckets list --project=<GCP_PROJECT_ID>`로 실제 이름 확인 |

자세한 Windows + Modal 배포 함정은 메모리 `modal_deploy_quirks.md` (Modal 배포 운영 quirks)를 참고.

---

## 6. 새 sub-agent 추가 시

1. `services/agents/agent-<name>/main.py` 생성 — §3 패턴 그대로
2. `scripts/sync_modal_secrets.py`의 `SECRET_MAPPINGS`에 `agent-<name>-secret` 항목 추가 (5키 동일 스키마)
3. `.env`에 5키 채움 → `python scripts/sync_modal_secrets.py agent-<name>-secret`
4. `modal deploy` → §4 검증

조장에게 별도 요청할 게 없도록 1회 setup(§1)으로 끝나게 설계됨. SA 권한이나 DB GRANT 추가가 필요하면 그때만 조장 호출.
