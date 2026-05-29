# ADR-0022: CI/CD WIF 신규 셋업 (dedicated SA) — 옵션 B 재사용 폐기

- **Status**: Accepted
- **Date**: 2026-05-29
- **Deciders**: @dhwang0803-glitch, @billionaireahreum
- **Tags**: area/infra, layer/cicd, security/wif

## Context

발표 덱 PART 04는 "PR Merge 3중 게이트(Ruff·TS·pytest 자동 차단) + Cloud Run staging 자동 배포 + Modal deploy 자동화" 가능을 명시. 그러나 본 프로젝트 `.github/workflows/` 실제 상태:

- 기존 yml 3종: `codegen-drift.yml`, `deploy-prod.yml`, `secret-scan.yml`
- **Cloud Run staging 자동 배포 0건** (`deploy-prod.yml`은 다른 프로젝트 `auto-workflow` AR 가리키는 stale 코드, 실행 이력 0회)
- **Modal deploy 자동화 0건**

CI/CD 4 workflow 신설 작업 계획서(PR #220, [`docs/ci-cd-automation-plan.md`](../../ci-cd-automation-plan.md)) v1 초안은 **"옵션 B (기존 prod WIF SA에 staging env IAM grant)"** 가정으로 작성됨. WIF pool/provider/SA 신규 생성 없이 기존 secret 재사용 + IAM role 추가만 하면 된다는 전제.

박아름(CI/CD 담당)이 사전 확인 중 옵션 B 전제 검증 → 다음 실측 결과로 **전제가 깨짐**을 발견:

> **검증 시점**: 2026-05-29 박아름 옵션 B 사전 확인 (셋업 직전). 본 ADR 채택·셋업 이후 시점에는 표의 "0개" 수치가 변경됨 (Secrets 4종 / Variables 2종이 셋업 후 박아름이 등록 완료, 본 ADR §Decision의 6종 표 참조).

| 검증 항목 | 결과 (셋업 직전) | 명령 |
|---|---|---|
| GCP `<GCP_PROJECT_ID>` WIF pool | **0개** | `gcloud iam workload-identity-pools list --location=global` Listed 0 items |
| GitHub repo Secrets | **0개** | `gh api repos/billionaireahreum/Workflow_Automation/actions/secrets` total_count: 0 |
| GitHub repo Variables | **0개** | `gh api .../actions/variables` total_count: 0 |
| `deploy-prod.yml` 실행 이력 | **1회 (2026-05-03 push to release, conclusion: failure)** | `gh api .../actions/workflows/deploy-prod.yml/runs` total_count: 1. AR repo + service명이 `auto-workflow*`로 하드코딩(`deploy-prod.yml:46-47`) — `GCP_PROJECT_ID`는 variable 기반이라 본 project ID도 가능했으나 실제로는 1회 실행 + 실패 후 방치. 재사용 가치 0 |

→ 재사용할 prod WIF SA·secret이 애초에 없음. 옵션 B 폐기 + 처음부터 신규 셋업 필요.

## Decision

**WIF Pool + Provider + dedicated SA + 5종 IAM role + impersonate 바인딩 6단계를 GCP `<GCP_PROJECT_ID>` project에 신규 셋업한다.** GitHub Actions runner는 WIF OIDC 토큰으로 dedicated SA `<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com`을 impersonate하여 Cloud Build / Cloud Run / Artifact Registry / GCS / IAM SA actAs를 수행한다.

### 셋업 6단계 (2026-05-29 황대원 실행 완료)

1. WIF Pool 생성 — `github-actions`
2. WIF Provider 생성 (GitHub OIDC) — `github`, **`attribute-condition="assertion.repository=='billionaireahreum/Workflow_Automation'"`** (보안 게이트)
3. dedicated SA 생성 — `<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com`
4. SA에 5종 project-level role grant — `roles/run.admin`, `roles/artifactregistry.writer`, `roles/iam.serviceAccountUser`, `roles/cloudbuild.builds.builder`, `roles/storage.objectAdmin`
5. WIF → SA impersonate 바인딩 — `roles/iam.workloadIdentityUser` + `principalSet://...attribute.repository/billionaireahreum/Workflow_Automation`
6. 검증 — provider describe + SA roles 5종 확인

GitHub Secrets 6종 신규 등록(박아름 담당, repo admin 권한). **본 ADR scope는 (a) WIF용 4종만**. (b) Modal용 2종은 별도 결정 영역(Modal CLI 인증)으로, 본 ADR과 같은 PR(#217)에서 묶여 등록되지만 결정 근거가 다름:

**(a) WIF용 4종 — 본 ADR scope**:
- Secret: `GCP_WIF_PROVIDER`, `GCP_WIF_SERVICE_ACCOUNT`
- Variable: `GCP_PROJECT_ID_PROD` (=`<GCP_PROJECT_ID>`), `GCP_REGION` (=`asia-northeast3`)

**(b) Modal용 2종 — 본 ADR scope 외 (modal-deploy.yml 인증)**:
- Secret: `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` (담당자 보유 Modal 토큰, [[memory:modal_shared_token]])

## Consequences

### Positive

- **SA 분리 원칙 정합** ([[memory:sub_agent_cloud_sql_iam]]) — CI/CD deploy SA가 api_server / worker / Modal sub-agent SA와 분리. 신규 서비스 SA 분리 표준 따름
- **repo-scoped 보안 게이트** — `attribute-condition`이 본 repo의 actions만 허용. 다른 repo가 fork해도 본 WIF 사용 불가
- **keyless 패턴** — SA JSON 키 발급 0건. 유출 surface 0. `gcloud iam service-accounts keys create` 호출 0회
- **7/1 destroy 정합** — 본 프로젝트는 [[memory:project_destroy_deadline]] 따라 2026-07-01 destroy. dedicated 리소스라 destroy 시 깔끔히 정리 (다른 프로젝트 IAM 영향 0)
- **인계 가능성** — 박아름이 `ci-cd-handoff-qa-2026-05-29.md` §2 표대로 GitHub Secrets 6종만 등록하면 즉시 사용. 황대원 GCP IAM 의존성 끊김

### Negative / Trade-offs

- **셋업 1회 60~90분** 추가 (옵션 B 채택 시 0분). 단, 1회성
- **project number / SA email enumeration 가능** — `projects/<GCP_PROJECT_NUMBER>/...` provider full path와 SA email이 인계 docs([`ci-cd-handoff-qa-2026-05-29.md`](../../ci-cd-handoff-qa-2026-05-29.md))에 평문 기록. **본 repo는 PUBLIC** (`gh repo view billionaireahreum/Workflow_Automation --json visibility` → `PUBLIC`). 즉 git history + PR comment로 인덱싱 가능. 실제 risk는 낮음(IAM 권한 없이는 무용한 식별자 + `attribute-condition`이 본 repo만 허용해 fork도 차단)이나 운영자가 인지하고 있어야 함
- **2026-06-02 GitHub Actions Node 24 강제 전환** 대비로 `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24="true"` env 워크플로우 yml에 명시 필요 (기존 `deploy-prod.yml` 패턴 차용)

### Follow-ups

- ☐ 박아름 GitHub Secrets 6종 등록 (PR #217 진행 중)
- ☐ Branch Protection Rules 등록 (release/development/main, [`ci-cd-automation-plan.md`](../../ci-cd-automation-plan.md) §4.5 참조) — 첫 워크플로우 실행 후
- ☐ 2026-07-01 프로젝트 destroy 시 WIF Pool + SA 정리 (Terraform 미관리, gcloud로 수동)
- ☐ 영구 운영 결정 시 — `lifecycle.ignore_changes = [image]` Terraform 추가 + tfvars 자동 갱신 자동화

## Alternatives Considered

- **옵션 A: 기존 prod WIF SA 재사용 (작업 계획서 v1 초안)** — **기각**. 재사용할 prod WIF가 애초에 없음(실측: WIF pool 0개 / Secrets 0개). `deploy-prod.yml`은 다른 프로젝트(`auto-workflow`) 가리키는 stale 코드로 본 repo에 잘못 commit된 흔적이라 한 번도 실행된 적 없음. 전제 자체 무효
- **옵션 B: SA JSON 키 발급 후 GitHub Secret 등록** — **기각**. (1) keyless 대비 유출 surface ↑ (Git history leak / Secret rotation 누락 등), (2) [[memory:sub_agent_cloud_sql_iam]] SA 분리 원칙 위반 가능, (3) Modal 토큰 외 GCP 키도 영구 저장돼야 함 — 운영 부담 증가
- **옵션 C (채택): WIF 신규 + dedicated SA** — keyless + repo-scoped + SA 분리 정합. 셋업 시간만 trade-off

## References

- PR [#220](https://github.com/billionaireahreum/Workflow_Automation/pull/220) — CI/CD 인계 패키지 (작업 계획서 + 입문서 + 박아름 Q&A) — `commit 6e1a8bf` 머지 2026-05-29
- PR #217 — CI/CD workflow 신설 (박아름 진행 중, deploy.yml + modal-deploy.yml 2종 + `deploy-prod.yml` 삭제)
- [`docs/ci-cd-automation-plan.md`](../../ci-cd-automation-plan.md) §4.1 — WIF 셋업 6단계 명령어
- [`docs/ci-cd-handoff-qa-2026-05-29.md`](../../ci-cd-handoff-qa-2026-05-29.md) §2 — 박아름 등록 값 표
- [`docs/ci-cd-explained.md`](../../ci-cd-explained.md) §2.4 — WIF 개념 + 5요소
- 검증 명령: `gcloud projects get-iam-policy <GCP_PROJECT_ID> --flatten="bindings[].members" --filter="bindings.members:github-actions-deploy@..." --format="value(bindings.role)"` → 5종 role 출력
