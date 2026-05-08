# Tester Agent 지시사항

## 역할
Developer Agent가 구현 파일을 작성한 후, 테스트를 실제로 실행하고 결과를 수집한다.
각 모듈의 계층별 테스트를 순서대로 실행한다.

---

## 실행 환경

```bash
# Python 가상환경 (모노레포 루트에서)
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# 각 모듈 개발 모드 설치
pip install -e packages/common_schemas/python
pip install -e "modules/auth[dev]"
pip install -e "modules/nodes_graph[dev]"
# ... 각 모듈별로 설치
```

---

## 모듈별 실행 순서

### 1단계: Foundation — common_schemas

```bash
pytest packages/common_schemas/python/tests/ -v 2>&1
ruff check packages/common_schemas/python/
```

common_schemas가 FAIL이면 나머지 모듈 테스트를 진행하지 않는다.

### 2단계: Domain Modules

```bash
# 각 모듈의 domain 레이어 (순수 단위 테스트, 외부 의존 없음)
pytest modules/auth/tests/unit/domain/ -v 2>&1
pytest modules/nodes_graph/tests/unit/domain/ -v 2>&1
pytest modules/ai_agent/tests/unit/domain/ -v 2>&1
pytest modules/toolset/tests/unit/domain/ -v 2>&1
pytest modules/doc_parser/tests/unit/domain/ -v 2>&1

# 각 모듈의 application 레이어 (Port mock)
pytest modules/auth/tests/unit/application/ -v 2>&1
pytest modules/nodes_graph/tests/unit/application/ -v 2>&1
pytest modules/ai_agent/tests/unit/application/ -v 2>&1
pytest modules/toolset/tests/unit/application/ -v 2>&1
pytest modules/doc_parser/tests/unit/application/ -v 2>&1
```

### 3단계: Storage — 통합 테스트 (DB 필요)

```bash
# DB 환경변수 필요: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
pytest modules/storage/tests/ -v 2>&1
```

DB 연결 실패 시 재시도 없이 즉시 Orchestrator에 보고한다.

### 4단계: Services

```bash
# api_server (httpx TestClient)
pytest services/api_server/tests/ -v 2>&1

# execution_engine (Celery eager mode)
pytest services/execution_engine/tests/ -v 2>&1
```

### 5단계: Frontend

```bash
cd services/frontend
npm run test 2>&1
npm run lint 2>&1
```

---

## 테스트 격리 규칙

| 테스트 유형 | DB 필요 | 외부 API 필요 | Mock 사용 |
|------------|--------|-------------|----------|
| `unit/domain/` | N | N | N (순수 로직) |
| `unit/application/` | N | N | Y (Port mock) |
| `integration/adapters/` | Y | Y (일부) | N (실제 연동) |
| `services/*/tests/` | Y | N | Y (modules mock 가능) |

---

## 결과 파싱 규칙

```bash
output=$(pytest <테스트 경로> -v 2>&1)

pass_count=$(echo "$output" | grep -c " PASSED")
fail_count=$(echo "$output" | grep -c " FAILED")
skip_count=$(echo "$output" | grep -c " SKIPPED")

echo "PASS: $pass_count, FAIL: $fail_count, SKIP: $skip_count"
```

---

## Lint 검증 (모든 Python 모듈 공통)

```bash
ruff check modules/ packages/ services/api_server/ services/execution_engine/ --config pyproject.toml
```

Ruff 규칙: `line-length=120`, Python ≥ 3.11

---

## Orchestrator에 전달할 결과 형식

```
[Tester 실행 결과]
- 실행 환경: Python 3.11+
- 실행 모듈: [모듈명 목록]

[모듈별 결과]
| 모듈 | 전체 | PASS | FAIL | SKIP |
|------|------|------|------|------|
| common_schemas | X | X | X | X |
| auth/domain | X | X | X | X |
| auth/application | X | X | X | X |
| ... | | | | |

[Lint 결과]
- Ruff: PASS / FAIL (N건)

FAIL 항목:
- [모듈:테스트 ID] [메시지]

다음 액션:
- FAIL 0건 → Refactor Agent 호출
- FAIL 존재 → Developer Agent 재호출 (재시도 N/3회)
```

---

## 주의사항

1. `.env` 파일의 접속 정보를 로그나 출력에 노출하지 않는다
2. DB 연결 실패 시 재시도 없이 즉시 Orchestrator에 보고한다
3. 도메인 테스트는 DB/외부 서비스 없이 반드시 실행 가능해야 한다
4. Frontend 테스트는 `services/frontend/` 디렉토리에서 실행한다
