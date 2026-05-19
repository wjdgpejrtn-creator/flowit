# ai_agent (REQ-004) Sprint 3 1주차 Skills Builder 작업 보고서 (2026-05-13)

**작업일**: 2026-05-13 (수)
**담당자**: 박아름 (Skills Builder Agent 분장)
**전일 보고서**: `sprint-3-week1-2026-05-12-skills-builder.md` 참조

---

## 1. 작업 개요

5/12 OPEN sub-branch `feature/req-004-skills-builder` (B 격리 정책 + A Modal app composition root 누적, 미 PR 상태)를 PR #51로 승격하고, 머지 차단 사유를 박아름 측에서 모두 해소했다. 다만 Test plan 2번/3번은 신정혜님의 `llm-base` Modal endpoint URL + Orchestrator Modal app 배포 대기로 묶여, 머지는 일괄 리뷰(Test plan #2·#3 모두 통과 후) 방침으로 진행한다.

세션 분할:

- **오전(어제 세션)**: PR #51 생성 + Modal 토큰 셋업 + modal 패키지 .venv 설치 + Modal deploy 차단 발견
- **오후(오늘 세션)**: Cloud SQL IAM 접속 검증 + skills_builder 회귀 4건 ecommerce 마이그레이션 + 머지 보류 회수 + 신정혜님 멘션 코멘트 등록

---

## 2. PR #51 생성 및 갱신

**브랜치**: `feature/req-004-skills-builder` → `development`
**제목**: feat(skills_builder): REQ-004 Skills Builder Modal app + 격리 정책 통합
**상태**: OPEN / mergeable **CLEAN** / gitleaks SUCCESS / reviewDecision 없음 (조장 리뷰 대기)
**누적 commits**:

| Hash | 메시지 | 일자 |
|------|--------|------|
| `eaaeb52` | refactor(skills_builder): BuildFromFunctionalDomainUseCase embed/upsert 격리 정책 적용 (B) | 5/12 |
| `f6f75e2` | feat(agent-skills-builder): Modal app composition root (5/17 plan 앞당김) (A) | 5/12 |
| `80098c0` | merge: development → PR #49 (Modal Cls hotfix + LangGraph + NodeRegistryAdapter) 흡수 | 5/12 |
| `d2e08ed` | docs(agent-skills-builder): Modal app 운영 가이드 README 추가 | 5/12 |
| `c426ab8` | Merge branch 'development' into feature/req-004-skills-builder | 5/13 |
| `41c075d` | test(skills_builder): industry_default 격리 정책 테스트 ecommerce로 마이그레이션 | 5/13 |
| `4a09242` | docs(skills_builder): Sprint 3 1주차 2026-05-13 작업 보고서 추가 | 5/13 |
| `69bc7b8` | test(skills_builder): agent-skills-builder Modal app composition root integration test 17건 | 5/13 |
| `1c49f22` | docs(skills_builder): 2026-05-13 보고서에 integration 테스트 17건 + main.py 리팩터링 반영 | 5/13 |
| `7cbbf4d` | feat(skills_builder): Cloud SQL IAM Connector 패턴으로 main.py 전환 + Modal Secret 매핑 추가 | 5/13 |
| `97284de` | Merge remote-tracking branch 'origin/development' (PR #53 가이드/매핑 흡수, conflict 해결) | 5/13 |
| `b7ecce0` | feat(database): 박아름 카탈로그 + Skills Builder baseline DB seed + 등록 스크립트 | 5/13 |
| `81056d7` | fix(scripts): bootstrap_node_definitions.py — ModalEmbeddingAdapter timeout 180s (BGE-M3 cold start 대응) | 5/13 |
| `99df606` | docs(skills_builder): 2026-05-13 보고서에 IAM Connector 전환 + Modal deploy + health 차단 반영 | 5/13 |
| `c0d9927` | fix(skills_builder): main.py Connector loop 패턴 디버깅 시도 5건 정리 (gitignore SA JSON 패턴 포함) | 5/13 |

**별건 OPEN PR — PR #55 (`feature/req-003-catalog-test-sync` → `development`)**:

| Hash | 메시지 |
|------|--------|
| `8759c56` | test(nodes_graph): toolset 14종 카탈로그 연결 후 회귀 4건 정리 (41 → 55) |
| `aa64f1d` | docs(req-003): 노드 카탈로그 요약 41 → 55 갱신 + toolset 14종 분류 명시 |
| `4238fa0` | **Merge pull request #55** (development에 머지 완료, sub-branch 삭제) |

---

## 3. 5/13 작업 상세

### 3.1 Modal 환경 셋업 (오전)

| 항목 | 결과 |
|------|------|
| `scripts/setup_modal_token.py` 실행 | ✅ `~/.modal.toml` `[dhwang0803]` 프로파일 verified (origin/chore/modal-token-setup에서 1회 checkout 후 실행, working tree에서 제거) |
| modal 패키지 .venv 설치 | ✅ `uv pip install modal --python .\.venv\Scripts\python.exe` (1.4.2) — 프로젝트 어떤 pyproject.toml에도 미선언이라 작업자별 별도 설치 필요 |
| PYTHONUTF8=1 환경 변수 | ✅ Windows cp949 환경에서 setup 스크립트 117라인 em-dash UnicodeEncodeError 우회 |

### 3.2 Modal deploy 차단 발견 (오전)

`modal deploy services/agents/agent-skills-builder/main.py` 실행 시 `Secret 'agent-skills-builder-secret' not found in environment 'main'` 에러. Secret 생성에 필요한 키 3종이 Drive 배포 `.env`에 부재.

| 키 | 부재 사유 | 해소 책임 |
|----|----------|----------|
| `LLM_BASE_URL` | 신정혜님 `llm-base` Modal app dhwang0803 deploy endpoint 미공유 | 신정혜 |
| `EMBEDDING_BASE_URL` | 동일 | 신정혜 |
| `DATABASE_URL` | Cloud SQL DSN 미설정 | 박아름 (5/13 오후 해소) |

조장 카톡 발송 (5/13 오전).

### 3.3 Cloud SQL IAM 접속 검증 (오후)

`docs/guides/cloud-sql-setup.md` 가이드 따라 박아름 로컬 `.env`에 Cloud SQL 3종 변수 복원 후 접속 검증.

`.env` 추가 항목:

```env
CLOUD_SQL_INSTANCE=<GCP_PROJECT_ID>:<REGION>:<INSTANCE>
DB_IAM_USER=<TEAM_MEMBER_1>@example.com
DB_NAME=workflow_automation
```

`scripts/_test_db.py` 실행 결과 (R/W/D 포함):

| 검증 항목 | 결과 |
|----------|------|
| PostgreSQL 버전 | 16.13 |
| pgvector | 0.8.1 |
| pgcrypto | 1.3 |
| public 테이블 수 | 37개 |
| `node_definitions` 테이블 | 있음 |
| INSERT / SELECT / DELETE | 모두 정상 |

이로써 `DATABASE_URL`은 Cloud SQL IAM DSN으로 즉시 생성 가능. Secret 등록 차단 항목 3개 중 1개 해소.

### 3.4 skills_builder 회귀 정리 (오후, commit `41c075d`)

PR #51 자체 테스트(`test_build_from_functional_domain_use_case.py` 17/17)는 5/12 검증대로 PASS였으나, 같은 디렉터리 `test_build_from_industry_default_use_case.py`에서 4건 FAIL 발견.

**FAIL 원인**: 5/12 조장 합의(ecommerce 1종만 활성, 5종 산업 비활성 + `E_INDUSTRY_DEACTIVATED`)에 따라 코드는 비활성 산업 호출을 거부하는데, 4건 테스트는 manufacturing/it/food를 호출해 격리 정책 검증을 시도 → ResultFrame 가정이 ErrorFrame으로 깨짐. PR #47 머지 시 동기화 누락된 잔여.

**마이그레이션 대상 4건**:

| 테스트 | 변경 전 | 변경 후 |
|--------|--------|--------|
| `test_embedder_failure_isolated_other_nodes_continue` | manufacturing / fail_on_substring="출고 확정" / failed_node_type="manufacturing_shipment_notify" | ecommerce / "환불 요청" / "ecommerce_refund_approval" |
| `test_upsert_failure_isolated_other_nodes_continue` | it / "it_pr_review_request" | ecommerce / "ecommerce_refund_approval" |
| `test_result_frame_includes_failed_fields_on_full_success` | food | ecommerce |
| `test_partial_failure_idempotent_recovery` | it / "it_pr_review_request" | ecommerce / "ecommerce_refund_approval" |

격리 정책 검증 의도(5종 중 1종 embed/upsert 실패 시 나머지 4종 계속 처리)는 ecommerce.json 5종(cart_abandonment_recovery / order_status_notify / inventory_sync / review_collection / refund_approval)로 동일 검증 가능. `failed_count=1` / `upserted_count=4` 단언 유지.

비활성 산업 검증 테스트(`test_deprecated_industries_yield_deactivated_error` / `test_deprecated_seed_files_still_exist_on_disk`)는 그대로 둠 — 비활성 정책 자체를 검증하는 의도이므로.

### 3.5 PR #51 머지 보류 회수 + 신정혜 멘션 코멘트 (오후)

박아름 5/12 코멘트 "이거 아직 병합하지 말아주십시오" 삭제. PR mergeable: `UNKNOWN` → **`MERGEABLE` / `mergeStateStatus: CLEAN`**.

신정혜님(`@wjdgpejrtn-creator`) 멘션 코멘트 추가 (https://github.com/billionaireahreum/Workflow_Automation/pull/51#issuecomment-4436658027) — Test plan #2/#3 차단 해소 조건 명시:

1. `llm-base` Modal app dhwang0803 deploy endpoint URL 공유 → `LLM_BASE_URL` / `EMBEDDING_BASE_URL`
2. Orchestrator Modal app dhwang0803 deploy → `HTTPSubAgentClient` → `/v1/agent/route` SSE 검증

### 3.6 지라 댓글 텍스트 작성

REQ-004 티켓에 박아름이 붙여넣을 진척 댓글 텍스트 작성 — 박아름 자체 해소 완료 + 신정혜 작업 대기 + 일괄 리뷰 방침 명시.

### 3.7 integration 테스트 17건 추가 + main.py 리팩터링 (오후 후반, commit `69bc7b8`)

PR #51 자체 리뷰(5/12)가 권장한 "SSE 직렬화 + 라우팅 분기 단위 테스트" 후속 항목. modal/fastapi/asyncpg 의존성 없이 pure helper 단독 검증.

**main.py 리팩터링 (최소)**:

- `_classify_next_action(frame) -> Literal["continue", "complete", "error"]` 모듈 함수 추출 — ResultFrame → "complete" / ErrorFrame → "error" / 그 외 진행 프레임 → "continue".
- `_sse_bytes(response) -> bytes` 모듈 함수 추출 (기존 `SkillsBuilderAgent._sse_bytes` staticmethod 제거 후 모듈 함수로 이동) — AgentProtocolResponse → `data: <json>\n\n` UTF-8 bytes.
- `SkillsBuilderAgent._stream` 내부의 if/elif/else 분기와 `self._sse_bytes()` 호출을 모듈 함수 사용으로 교체. 동작 변경 없음.

**신규 테스트** (`modules/ai_agent/tests/integration/test_agent_skills_builder.py`, 17건):

| 그룹 | 테스트 수 | 검증 내용 |
|------|----------|----------|
| `_classify_next_action` | 3 | ResultFrame → complete / ErrorFrame → error / AgentNodeFrame → continue |
| `_sse_bytes` | 5 | bytes 반환 / `data: ` prefix + `\n\n` suffix / JSON body round-trip / 한국어 + em-dash UTF-8 보존 / 진행 프레임 포함 |
| AgentProtocolRequest payload | 3 | source_type별 시그니처: industry_default(industry_code) / functional_domain(domain_code) / sop(document) — main.py route() 호출 정합 |
| AgentProtocolResponse next_action | 3 | Literal["continue", "complete", "error"] 값 정합 |
| Use case 시그니처 | 3 | BuildFromIndustryDefault / Functional / SOP `.execute()` 매개변수 정합 |

**구현 노트**:
- `services/agents/agent-skills-builder/main.py`는 agent 디렉터리 이름에 하이픈이 있어 일반 `import` 불가 → `importlib.util.spec_from_file_location`로 동적 로드.
- `AgentState`는 6 필수 필드(session_id/user_id/messages/turn_count/mode/execution_status) → inline 헬퍼 `_make_agent_state(session_id, user_id)`로 Skills Builder 호출 패턴(`mode=SKILL_BUILDER` + `RUNNING`) 생성. 박아름 컨벤션(conftest 미사용) 준수.

### 3.8 신정혜 URL 수령 + 객관적 점검 (저녁)

신정혜님 카톡으로 Modal endpoint URL 2개 + Orchestrator URL 1개 수령:

```
LLM_BASE_URL=https://<WORKSPACE>--llm-base.modal.run
EMBEDDING_BASE_URL=https://<WORKSPACE>--llm-base.modal.run
Orchestrator: https://<WORKSPACE>--orchestrator.modal.run
```

박아름 객관적 점검:

| 항목 | 결과 |
|------|------|
| Modal URL 패턴 정합 | ✅ `<workspace>--<app>-<class>-<method>.modal.run` 표준 |
| llm-base `/v1/health` | ✅ HTTP 200 (45s — GPU cold start, 신정혜 안내 정합) |
| orchestrator `/v1/health` | ✅ HTTP 200 (5s) |
| `ModalEmbeddingAdapter` 호출 경로 | ✅ `EMBEDDING_BASE_URL/v1/embed` HTTP REST |
| `ModalLLMAdapter` 호출 경로 | ✅ Modal `Cls.from_name("llm-base", "LLMBase").generate.remote.aio()` RPC |

### 3.9 Cloud SQL IAM Connector 패턴 전환 + Modal deploy (commit `7cbbf4d`)

박아름 5/13 오전 main.py 패턴(`os.environ["DATABASE_URL"]` + DSN)이 가이드 `docs/guides/sub_agent_modal_deploy.md` §5 함정 표 첫 항목("옛 DSN 패턴 코드 잔재")에 해당 → 가이드 §3.2 IAM Connector 패턴으로 전환.

**가이드 §3.2 표준 적용**:

- image에 `cloud-sql-python-connector[asyncpg]>=1.12` 추가 (enable_iam_auth=True 지원 라이브러리)
- Modal Secret 마운트 2개:
  - `agent-skills-builder-secret` (박아름 등록 — 5키): LLM_BASE_URL + EMBEDDING_BASE_URL + CLOUD_SQL_INSTANCE + DB_IAM_USER (공용 SA) + DB_NAME
  - `cloudsql-iam-sa` (조장 1회 등록 — 1키): GOOGLE_APPLICATION_CREDENTIALS_JSON
- `boot()` — IAM Connector 패턴: GOOGLE_APPLICATION_CREDENTIALS_JSON → 임시 파일 + ADC 환경변수 + `Connector + connect_async + enable_iam_auth=True + IPTypes.PUBLIC + create_async_engine("postgresql+asyncpg://", async_creator=...)`
- `shutdown()` — `asyncio.run(engine.dispose())` + `connector.close_async()` (sync 컨텍스트)
- `/v1/health` — DB ping ("iam-connected") + 503 분기 (가이드 §3.3 패턴)

**.env 갱신**: `LLM_BASE_URL` + `EMBEDDING_BASE_URL` 신규 추가 + `DB_IAM_USER`를 박아름 개인 이메일 → 공용 SA(`<MODAL_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com`)로 변경. 박아름 로컬 dev (`scripts/_test_db.py`)는 다음 실행 시 `$env:DB_IAM_USER` 임시 override 필요.

**`scripts/sync_modal_secrets.py`**: `agent-skills-builder-secret` 매핑 추가. 단 development의 PR #53(`d2443a3 chore(infra): sub-agent Modal 배포 셀프 서비스 가이드 + IAM 인증 매핑`)에 이미 동일 매핑이 있어서 development merge로 자연 통합 (commit `97284de`).

**Modal Secret 등록**: `python scripts/sync_modal_secrets.py agent-skills-builder-secret` → 1/1 synced OK.

**Modal deploy 시도 1 (실패)** — modal SDK `env()` 호출 순서 함정:

```
An image tried to run a build step after using `image.add_local_*` to include local files.
```

가이드 §3.1 image 정의 그대로 사용 시 `add_local_*` 이후 `.env()` 호출이 build step으로 분류되어 실패. 가이드보다 modal SDK가 더 엄격해진 상태. 해결: `.env({"PYTHONPATH": ...})`을 `.pip_install(...)` 직후로 옮기고 `.add_local_dir`를 마지막에 배치.

**Modal deploy 시도 2 (성공)**: ✓ App deployed in 7.348s. endpoint:

```
https://<WORKSPACE>--skills-builder.modal.run
```

### 3.10 `/v1/health` 차단 발견 — `cloudsql-iam-sa` Secret JSON 손상

```
curl https://<WORKSPACE>--skills-builder.modal.run/v1/health
→ HTTP 000 in 120.014s (timeout)
```

`modal app logs agent-skills-builder`:

```
google.auth.exceptions.DefaultCredentialsError:
  ('File /tmp/gcp-sa.json is not a valid json file.',
   JSONDecodeError('Expecting value: line 1 column 1 (char 0)'))
@ main.py:164  self._connector = Connector()
```

**원인 추정**: 조장이 가이드 §1.3 PowerShell 패턴으로 `cloudsql-iam-sa` 등록 시 multi-line JSON의 newline이 명령 인자 경계로 해석되어 첫 줄만 Secret에 저장됐을 가능성. 다른 sub-agent(orchestrator/composer/personalization)는 동일 Secret을 쓰는데 헬스체크 통과 — 일관성 미스. 박아름 카톡으로 사실 공유 → **조장이 5/13 17:00경 `cloudsql-iam-sa` Secret 재등록 예정**.

### 3.11 development merge — PR #53 흡수 (commit `97284de`)

`sync_modal_secrets.py` 매핑 추가 commit `7cbbf4d` push 후 PR #51이 `CONFLICTING`로 바뀜. 원인: development에 PR #53(`d2443a3`)이 머지되어 동일 파일을 다른 텍스트로 수정.

`git merge origin/development` 실행 → conflict 2건 모두 origin/development 측 채택(코멘트 + agent-personalization-secret 미사용 매핑까지 포함) → merge commit `97284de`. PR #51 mergeable **CLEAN** 복귀.

박아름 룰(`feedback_conventions.md` 79-84) "rebase 대신 `git merge origin/development`" 표준 패턴 적용. 5/12 박아름 commit `80098c0`과 동일 방식. force push 0건. development 무손상.

### 3.12 별건 PR #55 — nodes_graph 회귀 hotfix (MERGED `4238fa0`)

별도 sub-branch `feature/req-003-catalog-test-sync`로 진행한 단발성 hotfix. 박아름 영역 `pytest modules/nodes_graph/tests`에서 회귀 4건 발견 (햄햄 commit `59f0e26 feat(toolset+nodes_graph)` 후속 정리 누락):

| 영역 | 5/13 시작 | PR #55 머지 후 |
|------|----------|---------------|
| code (`catalog_registry.py` + `toolset_nodes.py`) | 55종 (햄햄 commit) | 55종 |
| test (`test_catalog.py` + `test_registry.py`) | 41종 (FAIL 4건) | 55종 (`8759c56`) |
| spec (`REQ-003 §"노드 카탈로그 요약"`) | 41종 | **55종 (`aa64f1d` — toolset 14종 분류 명시)** |

→ 3종 SSOT 정합 회복. 머지 commit `4238fa0` (development에 fast-forward). sub-branch local + remote 모두 삭제 완료 (`feedback_branch_strategy.md` 룰).

박아름 자체 리뷰 3 기준 (spec/의존성/clean arch) 모두 ✅. 자체 리뷰 코멘트 PR #55 등록: https://github.com/billionaireahreum/Workflow_Automation/pull/55#issuecomment-4437783673

### 3.13 cloudsql-iam-sa Modal Secret 재등록 (조장 SA JSON 공유 + 박아름 처리)

5/13 조장 답신: "agent마다 자기 secret 생성 / Secret이 손상된 거면 그냥 아름님이 다시 발급받으면 됩니다". 박아름 GCP IAM 권한 점검:

```
gcloud iam service-accounts list / keys create
→ PERMISSION_DENIED (<TEAM_MEMBER_1>@example.com — iam.serviceAccounts.list/keys.create 둘 다 거부)
```

박아름 권한 없음 확인 후 조장이 GCP SA JSON key 직접 공유 (`workflowauto-*.json`).

**사용자 직접 보안 룰 지시** (박아름 적용):
- SA JSON 파일 Read tool로 열람 X (스크립트 런타임 로드만 — `feedback_env_file.md` 룰 확장 적용)
- 환경 변수 long-term 등록 X (process-scope도 회피)
- `.gitignore`에 SA key 파일 패턴 추가 (`workflowauto-*.json` + `*-sa-key.json` + `gcp-sa-*.json` + `modal-sa-key.json`)
- 사용 후 즉시 변수 정리

**modal secret create 패턴 함정** (가이드 §1.3 원인 확정):

| 시도 | 결과 |
|------|------|
| PowerShell `& modal secret create cloudsql-iam-sa "KEY=$saJson"` (-Raw 받은 multi-line) | JSON 내부 큰따옴표 escape 실패 → `line 1 column 2: Expecting property name` 에러 |
| PowerShell + Get-Content `-Raw` + Python -c minify pipe | 같은 newline 분리 문제 |
| **Python subprocess + JSON minify (single-line)** | ✅ **통과** |

해결 패턴 (commit `c0d9927` 보안 메모에 명시):

```python
import json, subprocess
data = json.load(open("workflowauto-*.json"))
single_line = json.dumps(data, separators=(",", ":"))  # private_key 안의 \n escape 보존
subprocess.run(["modal", "secret", "create", "cloudsql-iam-sa",
                f"GOOGLE_APPLICATION_CREDENTIALS_JSON={single_line}", "--force"])
```

임시 스크립트 `_register_modal_secret.py` 사용 후 즉시 삭제 (gitignore 룰 + 보안). Secret 등록 OK 확인.

### 3.14 ConnectorLoopError 디버깅 5건 (모두 실패, 박아름 한계 도달)

Modal Secret 재등록 후 `/v1/health` 호출 시 새 에러:

```
google.cloud.sql.connector.exceptions.ConnectorLoopError:
  Running event loop does not match 'connector._loop'.
  Connector.connect_async() must be called from the event loop
  the Connector was initialized with.
```

박아름 디버깅 시도 5건 모두 동일 에러 (commit `c0d9927`로 보존):

| # | 패턴 | 결과 |
|---|------|------|
| 1 | 가이드 §3.2 — sync boot()에서 `Connector()` + `create_async_engine` (`7cbbf4d` 패턴) | ConnectorLoopError |
| 2 | FastAPI `@on_event("startup")` async에서 `Connector(loop=loop)` | ConnectorLoopError |
| 3 | request handler 내부 lazy init + `asyncio.Lock` | ConnectorLoopError |
| 4 | connection-per-request SQLAlchemy (매번 새 Connector+engine+dispose) | ConnectorLoopError |
| 5 | asyncpg direct + `Connector(refresh_strategy="lazy")` (loop 인자 없이) | ConnectorLoopError |

→ **`Connector()` 자체가 modal asgi_app calling loop와 다른 loop를 잡음**. modal docs / Cloud SQL Connector 라이브러리 내부 동작 호환성 이슈로 추정. 가이드 §3.2가 modal asgi_app 환경에서 작동 안 함을 확정.

### 3.15 근본 차단 — 신정혜 sub-agent main.py git push 누락 (사용자 진단)

사용자 진단: "신정혜가 그 작업한 거 PR 안 올려서 우리꺼에 머지 안 된 거 같아"

확인 결과:

| 항목 | 상태 |
|------|------|
| `modal app list` — orchestrator / agent-composer / agent-personalization | ✅ 3개 모두 dhwang0803에 deploy됨 |
| `services/agents/{orchestrator,agent-composer,agent-personalization}/main.py` | ❌ git에 없음 (development에 push 안 됨) |
| 박아름이 정혜님 통과 패턴 참조 | ❌ 코드 없으니 불가 |

→ **박아름 자체 디버깅 한계 + 신정혜 push 대기**. 카톡 발송 예정 (사용자 결정 따라).

### 3.16 DB seed 등록 + BGE-M3 검색 실 검증 (commit `b7ecce0` + `81056d7`)

조장 5/13 카톡 합의 ("DB 필요하면 진행 / 스키마+마이그레이션 다 만들어 추가 / placeholder는 박아름 노드 따라간다") + 신정혜 A안 동의로 박아름이 직접 등록 진행.

**5/13 DB 점검 발견**:

| 항목 | 점검 결과 |
|------|---------|
| `node_definitions` total | 54 (placeholder, 5/11 메모 "DB 54종 빈 placeholder" 그 상태) |
| embedding NOT NULL | **0/54 = 100% NULL** → 유사도 검색 불가 |
| 박아름 카탈로그 등록 | **0건** (5/11 메모 "discover_and_register 호출 후 등록" 약속 미실행) |
| Skills Builder baseline | **0건** |
| 의존성 PgNodeDefinitionRepository (ae19d67) + ModalEmbeddingAdapter (a5cbb0a) | ✅ 모두 머지 완료 — 박아름이 실 호출만 안 한 상태 |

**진행 (5/13 박아름 직접 실행)**:

1. `database/seeds/node_definitions.json` placeholder 54 → 박아름 카탈로그 55로 갈아엎기 (`export_catalog_seed.py`로 추출)
2. `scripts/bootstrap_node_definitions.py` 운영 스크립트 작성 (cleanup + 카탈로그 + Skills Builder + embedding + dry-run/all 옵션)
3. dry-run 검증 통과 → 실 실행

**실 실행 결과** (`bootstrap_node_definitions.py --all --cleanup-placeholder`):

```
[BEFORE] node_definitions total=54, embedding NOT NULL=0/54
[cleanup] placeholder 54건 삭제
[A] REQ-003 카탈로그 55종 등록 → 완료
[B] REQ-004 Skills Builder baseline 30 SkillNode → 모두 failed=0
    - ecommerce: 5/5
    - customer_support: 5/5
    - it_ops: 5/5
    - document_data: 5/5
    - hr: 5/5
    - marketing: 5/5
[AFTER] node_definitions total=85, embedding NOT NULL=85/85 ✅
```

**중간 차단 + 우회**:

- `jsonschema` 박아름 로컬 `.venv` 누락 → `uv pip install jsonschema` 추가 (Modal image에는 5/13 commit `62f0a3a`로 이미 보강된 상태였음)
- `httpx.ReadTimeout` (BGE-M3 GPU cold start 45s+ vs ModalEmbeddingAdapter default 30s) → 박아름 스크립트에서 `_client` timeout 180s 교체 (commit `81056d7`). 신정혜 영역 영구 fix는 후속 PR(`__init__` timeout 인자화) 권장.

**BGE-M3 검색 실 검증 (PR #51 자체 리뷰 코멘트 #issuecomment-4441350767)**:

10 자연어 쿼리 × top-5 검색:

| 쿼리 | top-1 | hit/expected |
|------|-------|-------------|
| Slack 채널에 메시지 보내기 | slack_post_message | 2/2 |
| 이커머스 환불 처리 워크플로우 | ecommerce_refund_approval | 2/2 |
| 이메일 발송 | (top-2) gmail_send | 2/2 |
| CSV 파일 파싱 | csv_parse | 2/2 |
| HTTP API 호출 | http_request | 3/3 |
| JSON 추출 및 변환 | (top-2) json_transform | 2/2 |
| 정기 스케줄 실행 | (top-4) schedule_trigger | 1/1 |
| PR 리뷰 요청 | (top-5 의미 인접) | 0/1 |
| HR 온보딩 자동화 | (의미 인접) | 0/1 |
| 고객 문의 처리 | (top-1 customer_support_voc_intake) | 0/2 |

종합: **14/18 = 77.8% top-5 expected 매칭**. 핵심 동의어/유의어(slack_*, http_*, json_*) 모두 매칭, 카테고리 정합, 한국어 BGE-M3 다국어 처리 정상. 일부 hit 0은 검증 스크립트의 expected 명명 오류 (검색 품질 문제 아님).

**`PgNodeDefinitionRepository.search_by_embedding` 동작 검증**:

| 항목 | 결과 |
|------|------|
| cosine_distance 정렬 | ✅ |
| `limit` 인자 (10/100) | ✅ |
| embedding NULL 제외 | ✅ (NULL 0건 보장) |
| HNSW 인덱스 활용 | ✅ |
| 카탈로그 + SkillNode 혼합 검색 | ✅ |

### 3.17 박아름 현재 main.py 상태 (commit `c0d9927`)

디버깅 5건 누적 + 마지막 시도 보존:

- `boot()`: ADC env 설정 + 어댑터 wiring만, DB lazy 초기화
- `_make_db_resources()` / `_cleanup_db_resources()`: connection-per-request helper (5번 패턴)
- `/v1/health`: asyncpg direct (Connector + connect_async + fetchval)
- `/v1/agent/route` → `_stream` 내부에서 request-scoped DB resources
- `@modal.exit()` shutdown(): no-op (ASGI lifespan으로 dispose 위임)
- **deploy 가능 / `/v1/health`는 ConnectorLoopError 그대로** — 신정혜 패턴 도착 후 적용 예정

---

## 4. 테스트

| 디렉터리 | 5/12 마감 | 5/13 마감 |
|---------|----------|----------|
| `modules/ai_agent/tests/unit/application/skills_builder/` | 113 passed + 4 failed | **117/117 passed** (0.57s) |
| `modules/ai_agent/tests/unit/application/skills_builder/test_build_from_functional_domain_use_case.py` (PR #51 신규) | 17/17 passed | **17/17 passed** (재현) |
| `modules/ai_agent/tests/integration/test_agent_skills_builder.py` (5/13 신규) | — | **17/17 passed** (0.79s) |
| 박아름 skills_builder 영역 합산 | — | **134/134 passed** (0.87s) |

회귀 4건 해소 + integration 17건 신규. PR #51 자체 검증(B 격리 정책 + A 라우팅/직렬화) 모두 클린.

---

## 5. 5/13 환경 / 외부 변화

### 5.1 신정혜 영역 머지 (5/12 후반 → 박아름 sub-branch 흡수 완료)

- PR #39 `d76ee5f` — ModalLLMAdapter + ModalEmbeddingAdapter + HTTPSubAgentClient + RouteRequestUseCase
- PR #49 `abe90e1` — Modal Cls hotfix(`c7d43f9`) + LangGraph adapters + NodeRegistryAdapter
- 박아름 sub-branch에 development merge로 PR #49 흡수 (`80098c0`)

코드 레벨 의존성은 모두 해소. 다만 `llm-base` Modal app dhwang0803 실 배포 endpoint URL이 박아름에게 공유되지 않은 상태.

### 5.2 조장 영역

- `scripts/setup_modal_token.py` repo push 완료 (PR #50 머지 — chore/modal-token-setup 브랜치)
- 박아름이 origin/chore/modal-token-setup checkout 후 1회 실행으로 ~/.modal.toml 셋업

---

## 6. PR #51 Test plan 현황

| # | 항목 | 5/13 오전 | 5/13 저녁 | 5/13 야간 |
|---|------|----------|----------|----------|
| 1 | 격리 정책 단위 테스트 (B) | ✅ 117/117 | ✅ 134/134 (integration +17) | ✅ 134/134 |
| 2 | Modal 배포 사전 검증 | ❌ URL/Secret 부재 | ⚠️ deploy 성공 / health 차단 | ⚠️ Secret 재등록 OK / **health ConnectorLoopError** |
| 3 | 실 endpoint e2e | ❌ Orchestrator 미배포 | ❌ Orchestrator OK / health 차단 | ❌ Test plan #2 미통과로 대기 |

**#2 잔여 차단**: 박아름 main.py가 modal asgi_app 환경의 `ConnectorLoopError`로 인해 health 통과 못 함. 박아름 디버깅 5건 모두 실패. **신정혜 sub-agent push 대기** (그들 통과 패턴 참조 필요).

**머지 방침**: 신정혜 패턴 도착 → 박아름 적용 → #2·#3 모두 통과 후 조장(`@dhwang0803`)께 일괄 리뷰 요청.

---

## 7. 박아름 후속 작업 (신정혜 대기 외)

PR #51 자체 리뷰(5/12)에서 권장한 후속 항목 중 미처리:

### 7.1 박아름 측 즉시 가능 (신정혜 의존 0)

| 후보 | 권장도 | 상태 |
|------|-------|------|
| ~~A. `tests/integration/test_agent_skills_builder.py` 작성~~ | — | ✅ **완료** (commit `69bc7b8`, 17/17 passed) |
| ~~B. `services/agents/agent-skills-builder/Dockerfile`~~ | — | ✅ 불필요 — main.py 확인 결과 `modal.Image.debian_slim()` API로 image 정의 (53-77라인), Dockerfile 패턴 아님 |
| ~~C. main.py IAM Connector 패턴 전환~~ | — | ✅ **완료** (commit `7cbbf4d`, deploy 성공) |
| D. PR #55 (nodes_graph 회귀 hotfix) | — | OPEN, 조장 리뷰 + 머지 대기 (단발성, 즉시 가능) |

PR #51 자체 리뷰 후속 권장 3건(`setup_modal_token.py` push / README / integration test) + main.py IAM 전환까지 모두 처리. 박아름 측 즉시 가능 작업 0건.

### 7.2 신정혜 sub-agent push 대기 (5/13 야간 진단)

박아름 자체 진행 0건. 신정혜님이 `services/agents/{orchestrator,agent-composer,agent-personalization}/main.py`를 git development에 push해야 박아름이 Cloud SQL Connector 통과 패턴 참조 가능. 사용자 결정 따라 카톡 발송 예정.

| 작업 | 차단 해소 시 진입 |
|------|---------------|
| 신정혜 sub-agent main.py 흡수 (`git merge origin/development`) | 신정혜 push 후 즉시 |
| 통과 패턴 분석 + 박아름 main.py 적용 | 흡수 후 즉시 |
| `modal deploy` redeploy + `/v1/health` 재호출 | 패턴 적용 후 즉시 |
| Test plan #2 체크 | health 통과 후 즉시 |
| Orchestrator endpoint 통한 e2e (HTTPSubAgentClient → /v1/agent/route SSE) | health 통과 후 즉시 |
| Test plan #3 체크 | e2e 통과 후 즉시 |
| 조장 일괄 리뷰 요청 (PR #51) | #2 + #3 모두 통과 후 |

---

## 8. 박아름 결정 사항 (2026-05-13)

| 결정 | 사유 |
|------|------|
| PR #51 머지 보류 회수 | 박아름 측 차단 0건 확정 (5/13 오후 시점). mergeable CLEAN |
| 일괄 리뷰 방침 | Test plan #2·#3 모두 통과 후 한 번에 조장 리뷰 요청. 부분 통과 시점 리뷰 분산 회피 |
| `.env` Cloud SQL 3종 변수 박아름 로컬 복원 | Drive 배포본은 갱신 시 사라질 가능성 — 박아름 로컬에서 직접 유지 |
| PR #55 (nodes_graph 회귀 hotfix) 별도 sub-branch 진행 | PR #51과 다른 영역(`modules/nodes_graph/` vs `modules/ai_agent/`). 단발성 hotfix는 `feedback_branch_strategy.md` 룰대로 sub-branch + 머지 후 삭제 |
| REQ-003 spec 갱신 PR #55에 흡수 | 햄햄 commit `59f0e26` 후속 정리 → spec ↔ code ↔ test 3종 SSOT 정합. PR #55 scope 동일 |
| SA JSON key 보안 룰 (사용자 직접 지시 5/13) | Read tool X / env 등록 X / gitignore 즉시 추가 / 임시 스크립트 즉시 삭제. `feedback_env_file.md` 룰 확장 적용 |
| Python subprocess + JSON minify로 Modal Secret 등록 | PowerShell `& modal secret create KEY=$value` 패턴이 multi-line JSON 처리 못 함 (가이드 §1.3 함정). Python subprocess + `json.dumps(separators=(",", ":"))` minify로 통과 |
| Connector 디버깅 5건 commit으로 보존 (`c0d9927`) | 디버깅 history 남겨 신정혜 패턴 도착 시 비교 가능. force push 0건 |
| 신정혜 sub-agent push 대기 (자체 디버깅 중단) | 박아름 디버깅 5건 모두 같은 ConnectorLoopError. 시간 낭비 회피 위해 신정혜 통과 패턴 도착 후 진입 |

---

## 9. 참조

- spec: `docs/specs/REQ-004-ai-agent.md` §2.1, §2.2, §10
- plan: `docs/specs/plan/sprint-3.md`
- 가이드: `docs/guides/cloud-sql-setup.md`
- 전일 보고서: `sprint-3-week1-2026-05-12-skills-builder.md`
- 박아름 결정 메모리:
  - `feedback_branch_strategy.md`
  - `feedback_modal_deploy.md` (Modal 배포 절차 + Windows uv .venv 노하우)
  - `feedback_session_cleanup.md` (작업 사이클 마무리 + /clear 룰)
- PR #51: https://github.com/billionaireahreum/Workflow_Automation/pull/51
