# services/common

Modal sub-agent app들이 공유하는 부트스트랩 헬퍼.

## gcp_secrets.py

GCP Secret Manager에서 secret 값을 pull해 `os.environ`에 주입한다. Modal app은 ADC용 `gcp-sa-key` Modal Secret 하나만 마운트하면 나머지 환경 변수는 Secret Manager에서 런타임에 읽는다.

### 사용 패턴

```python
from services.common.gcp_secrets import load_secrets_to_env

@modal.enter()
def boot(self) -> None:
    # 1) SA JSON → 임시파일 → GOOGLE_APPLICATION_CREDENTIALS 환경변수 (ADC)
    sa_payload = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
    sa_path = Path(tempfile.gettempdir()) / "gcp-sa.json"
    sa_path.write_text(sa_payload, encoding="utf-8")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa_path)

    # 2) GCP Secret Manager → 환경변수 주입
    load_secrets_to_env({
        "llm-base-url":       "LLM_BASE_URL",
        "embedding-base-url": "EMBEDDING_BASE_URL",
        "cloud-sql-instance": "CLOUD_SQL_INSTANCE",
        "db-iam-user":        "DB_IAM_USER",
        "db-name":            "DB_NAME",
    })
    # 이후 코드가 os.environ["LLM_BASE_URL"] 등을 그대로 사용
```

### project_id 해석 순서

1. 함수 인자 `project_id`
2. 환경 변수 `GOOGLE_CLOUD_PROJECT`
3. ADC 기본 프로젝트 (SA key payload)

### Modal image에 마운트

```python
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("google-cloud-secret-manager>=2.20", ...)
    .env({"PYTHONPATH": "/repo:/repo/modules"})
    .add_local_dir("services/common", remote_path="/repo/services/common")
    .add_local_dir("modules", remote_path="/repo/modules")
)
```

`/repo`가 PYTHONPATH에 있으면 `from services.common.gcp_secrets import ...`로 import 가능 (PEP 420 namespace package).

### 테스트

```
pytest services/common/tests/
```

dev 머신에 `google-cloud-secret-manager` 없어도 통과 — 헬퍼가 lazy import + 테스트는 `sys.modules`에 stub 주입.
