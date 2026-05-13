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

---

## 4. 테스트

| 디렉터리 | 5/12 마감 | 5/13 마감 |
|---------|----------|----------|
| `modules/ai_agent/tests/unit/application/skills_builder/` | 113 passed + 4 failed | **117/117 passed** (0.57s) |
| `modules/ai_agent/tests/unit/application/skills_builder/test_build_from_functional_domain_use_case.py` (PR #51 신규) | 17/17 passed | **17/17 passed** (재현) |

회귀 4건 해소. PR #51 자체 검증(B 격리 정책) + skills_builder 디렉터리 전체 클린.

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

| # | 항목 | 상태 | 차단 |
|---|------|------|------|
| 1 | 격리 정책 단위 테스트 (B) | ✅ 117/117 passed | — |
| 2 | Modal 배포 사전 검증 | ❌ 차단 | `LLM_BASE_URL` + `EMBEDDING_BASE_URL` (신정혜 대기) — `DATABASE_URL`은 박아름 확보 완료 |
| 3 | 실 endpoint e2e (`HTTPSubAgentClient` → `/v1/agent/route` SSE) | ❌ 차단 | Orchestrator Modal app dhwang0803 deploy (신정혜 대기) |

**머지 방침**: 위 2)·3) 모두 통과시킨 후 조장(`@dhwang0803`)께 일괄 리뷰 요청.

---

## 7. 박아름 후속 작업 (신정혜 대기 외)

PR #51 자체 리뷰(5/12)에서 권장한 후속 항목 중 미처리:

### 7.1 박아름 측 즉시 가능 (신정혜 의존 0)

| 후보 | 권장도 | 비고 |
|------|-------|------|
| **A. `tests/integration/test_agent_skills_builder.py` 작성** | ★★★ | PR #51 자체 리뷰 "SSE 직렬화 + source_type 분기 단위 테스트" 권장. mock으로 LLM/Embedder/Repo 격리 가능. PR #51에 흡수 commit |
| B. `services/agents/agent-skills-builder/Dockerfile` | ★☆☆ | Modal app은 보통 `modal.Image` API로 image 정의해 Dockerfile 불필요한 패턴. main.py 확인 후 판단 |

### 7.2 신정혜 대기 작업 (URL 받으면 즉시 가능)

| 작업 | 차단 해소 시 진입 |
|------|---------------|
| `agent-skills-builder-secret` Modal Secret 등록 | LLM/EMBED URL 도착 → `modal secret create ... LLM_BASE_URL=... EMBEDDING_BASE_URL=... DATABASE_URL=...` |
| `modal deploy services/agents/agent-skills-builder/main.py` 재시도 | Secret 등록 후 즉시 |
| Test plan #3 e2e 검증 | Orchestrator 배포 후 즉시 |

---

## 8. 박아름 결정 사항 (2026-05-13)

| 결정 | 사유 |
|------|------|
| PR #51 머지 보류 회수 | 박아름 측 차단 0건 확정. mergeable CLEAN |
| 일괄 리뷰 방침 | Test plan #2·#3 모두 통과 후 한 번에 조장 리뷰 요청. 부분 통과 시점 리뷰 분산 회피 |
| `.env` Cloud SQL 3종 변수 박아름 로컬 복원 | Drive 배포본은 갱신 시 사라질 가능성 — 박아름 로컬에서 직접 유지 |

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
