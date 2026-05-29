# CI/CD 입문 — 본 작업 이해를 위한 가이드

**작성일**: 2026-05-29
**작성자**: 황대원 (조장)
**대상**: CI/CD 개념을 처음 접하는 팀원
**관련 문서**: [ci-cd-automation-plan.md](./ci-cd-automation-plan.md) (실제 작업 계획서)

---

## 1. CI/CD가 도대체 뭔가

### 1.1 단어 풀이

- **CI = Continuous Integration (지속적 통합)** — 코드 변경이 main 브랜치에 들어오기 전에 **자동으로 검사**하는 것
- **CD = Continuous Deployment/Delivery (지속적 배포)** — 검사 통과한 코드를 **자동으로 서버에 올리는** 것

### 1.2 CI/CD가 없는 세계 (지금 우리 프로젝트의 실제)

지금 우리 프로젝트가 정확히 이렇게 굴러가고 있다:

```
1. 개발자 A가 PR을 올림
2. 리뷰어가 "ruff 돌려봤어?" "pytest 통과해?" 손으로 묻는다
3. 개발자 A가 자기 노트북에서 ruff/pytest 돌리고 "통과했어요" 답한다
   → 사실 안 돌렸을 수도 있고, 자기 머신에서만 통과했을 수도 있다
4. 리뷰어가 merge 클릭
5. 누군가 staging에 배포하고 싶으면 자기 노트북에서 직접
   gcloud builds submit / gcloud run deploy / modal deploy 실행
   → 이걸 안 하면 코드만 머지되고 staging은 그대로 옛날 버전
```

이게 우리가 매번 손으로 하던 일이다. **그래서 두 가지 사고가 일어남**:

- **code_change_deploy_verify 패턴** — 코드 머지하고 배포 잊어서 다음 배포 때 surprise crash (composer 5/26 사고)
- 리뷰에서 "ruff 통과 확인했나" 같은 걸 사람이 일일이 묻는 비효율

### 1.3 CI/CD가 있는 세계

```
1. 개발자 A가 PR을 올린다
2. GitHub이 자동으로:
   - ruff (코드 스타일) 검사
   - pytest (테스트) 실행
   - TypeScript 검사
   → 하나라도 빨간 X가 뜨면 머지 버튼이 잠긴다
3. 통과하면 리뷰어가 merge 클릭
4. release 브랜치에 머지하면 자동으로:
   - Docker 이미지 빌드
   - Artifact Registry에 푸시
   - Cloud Run staging에 새 revision 배포
   - Modal sub-agent 재배포
5. 사람은 "release 머지 클릭"만 한다. 배포는 GitHub이 한다
```

**이게 본 작업의 목표.** 발표 덱 PART 04에 "PR 3중 게이트 + Cloud Run 자동 배포 + Modal 자동 배포 다 됩니다"라고 적혀있는데 실제로는 안 돼있어서, 이걸 진짜로 만들어 두는 작업.

---

## 2. CI/CD를 굴러가게 하는 부품들

### 2.1 GitHub Actions (CI/CD의 엔진)

GitHub이 제공하는 자동화 도구. `.github/workflows/*.yml` 파일에 "**언제 어떤 명령을 실행할지**"를 적어두면, GitHub이 그 트리거가 발동될 때마다 자기 서버(=runner)에서 그 명령을 실행해준다.

```yaml
on:                        # 언제?
  pull_request:            # PR 올라오면
jobs:
  ruff:                    # 어떤 작업?
    runs-on: ubuntu-latest # GitHub 서버에서
    steps:
      - run: ruff check .  # 이 명령 실행
```

이 yml 파일 4개를 만드는 게 본 작업의 핵심.

### 2.2 runner (실행 머신)

GitHub Actions는 PR이 올라올 때마다 새 우분투 VM을 띄워서 거기서 작업을 실행하고 끝나면 버린다. **즉, 매 실행마다 깨끗한 머신** — 의존성 install부터 다 새로 해야 함. 이것 때문에 pytest yml의 install 단계가 12개 패키지나 되는 거다.

### 2.3 GitHub Secrets / Variables

GitHub Actions 안에 비밀번호나 토큰을 적어둘 수 있는 안전한 저장소. yml 파일에는 `${{ secrets.GCP_WIF_PROVIDER }}` 같은 placeholder만 적고 실제 값은 GitHub Settings → Secrets에 등록.

- **Secret**: 값이 마스킹돼 노출 안 됨 (예: API 토큰)
- **Variable**: 평문 노출 OK (예: `GCP_PROJECT_ID`)

### 2.4 WIF (Workload Identity Federation)

GCP의 인증 방식. GitHub Actions runner가 "내가 황대원 팀의 GitHub Actions야"라고 GCP한테 증명하면, GCP가 임시 자격증명을 발급해주는 구조. **service account key json을 GitHub에 박지 않아도 되는 안전한 패턴.**

```
GitHub runner
   ↓ "내가 우리 repo의 release 브랜치에서 돌아가는 actions임" 토큰 제시
GCP WIF Provider
   ↓ "OK, 이 service account 가짜 키 줄게"
WIF Service Account (= deploy 권한 가진 GCP SA)
   ↓
gcloud builds submit 등 실행 가능
```

**본 프로젝트는 WIF가 한 번도 셋업된 적 없음** (작업 계획서 초안의 "옵션 B 재사용" 전제 폐기). 실측:
- `gcloud iam workload-identity-pools list --project=<GCP_PROJECT_ID> --location=global` → Listed 0 items
- `gh api repos/billionaireahreum/Workflow_Automation/actions/secrets` → total_count: 0
- 기존 `deploy-prod.yml`은 다른 프로젝트(`auto-workflow`) 가리키는 stale 코드 — 실행된 적 없음

→ **WIF Pool/Provider/SA + GitHub Secrets 6종 전부 신규 생성** (담당자 60~90분 작업).

WIF 구성 5요소:
1. **WIF Pool** — GitHub Actions 같은 외부 ID 발급원들을 묶는 컨테이너
2. **WIF Provider** — GitHub OIDC 토큰을 받아 검증하는 부품. `attribute-condition`으로 "본 repo의 actions만 허용" 같은 보안 제한 박음
3. **Service Account (deploy 권한)** — Cloud Run 갱신/AR push 권한 가진 GCP 계정
4. **5종 IAM role grant** — SA에 run.admin / artifactregistry.writer / iam.serviceAccountUser / cloudbuild.builds.builder / storage.objectAdmin
5. **impersonate 권한** — WIF가 SA를 흉내낼 수 있게 `roles/iam.workloadIdentityUser` + principalSet 바인딩

5개 중 하나라도 빠지면 deploy 401 또는 "unable to acquire impersonated credentials" 에러. 작업 계획서 §4.1에 6단계 명령어 다 박혀있음.

### 2.5 Branch Protection Rules

GitHub Settings → Branches → main/development/release에 "이 status check 통과 안 하면 머지 못함"이라고 설정하는 기능. **CI 워크플로우를 만든 다음에 반드시 이걸 켜야 효력 발생.** 켜지 않으면 빨간 X가 떠도 머지 버튼 활성화돼 있다.

---

## 3. 본 작업: 4개 yml 파일 + 1개 삭제

실제 작업 계획서 §3 풀이.

### 3.1 ruff.yml (PR 게이트 #1)
- **무엇**: PR 올라올 때마다 ruff 돌려서 코드 스타일 위반/format 어긋남 체크
- **왜**: 손으로 매번 ruff 돌리는 거 잊어버려서 main이 더러워지는 걸 차단
- **트리거**: `pull_request` + `push: [main, development]`

### 3.2 pytest.yml (PR 게이트 #2)
- **무엇**: PR 올라올 때마다 backend pytest(PG container 띄워서) + frontend jest 둘 다 실행
- **왜**: 테스트 깨진 코드가 머지되는 사고 차단
- **어려운 이유**: 백엔드는 PostgreSQL이 필요. GitHub runner에 `pgvector/pgvector:pg16` 컨테이너를 띄우고, 22개 schema migration 적용한 다음 pytest 실행하는 절차가 필요. **이게 4개 작업 중 가장 까다로움**

### 3.3 deploy.yml (CD #1 — Cloud Run)
- **무엇**: release 브랜치에 머지되면 자동으로 Cloud Build → Cloud Run staging 갱신
- **왜**: 지금은 코드 머지하고 배포 잊는 사고가 반복됨. 자동화하면 release 머지 = 배포 시점이 명확
- **트리거**: `push: release` (FF only). dev push 자동 배포 안 함 — 데모 시연 중에 우발적 배포 차단

### 3.4 modal-deploy.yml (CD #2 — Modal)
- **무엇**: release 머지되면 5개 Modal sub-agent (composer, orchestrator, skills-builder, personalization, llm-base)를 자동 재배포
- **왜**: 위와 동일 + Modal은 더 자주 잊혀짐 (Cloud Run과 다른 명령어라)

### 3.5 deploy-prod.yml 삭제
- **무엇**: 기존에 있던 `deploy-prod.yml`이 다른 프로젝트(`auto-workflow`)를 가리키는 stale 코드. 본 repo에 잘못 commit된 거. 본 프로젝트에 prod Cloud Run 0건이라 무관 → 삭제

---

## 4. 사전 준비 (담당자가 해야 할 일)

실제 작업 계획서 §4와 §8 정리.

### 4.1 GCP WIF 신규 셋업 (작업 계획서 §4.1)

본 프로젝트에 WIF가 없으므로 **6단계 신규 셋업** (60~90분):

1. **WIF Pool 생성** (`github-actions`)
2. **WIF Provider 생성** — GitHub OIDC. `attribute-condition`으로 `billionaireahreum/Workflow_Automation` repo만 허용 (보안 핵심)
3. **Deploy SA 신규 생성** (`<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com`)
4. **SA에 5종 role grant**:
   - `roles/run.admin` (Cloud Run 갱신)
   - `roles/artifactregistry.writer` (이미지 푸시)
   - `roles/iam.serviceAccountUser` (런타임 SA actAs)
   - `roles/cloudbuild.builds.builder` (Cloud Build 호출)
   - `roles/storage.objectAdmin` (Cloud Build 컨텍스트 업로드)
5. **WIF → SA impersonate 허용** (`roles/iam.workloadIdentityUser` + principalSet 바인딩)
6. **셋업 검증** (provider describe + SA role 5종 확인)

명령어 전체는 작업 계획서 §4.1 참조.

**가장 흔한 함정**: §2 attribute-condition 누락. 누락 시 임의 GitHub repo가 우리 GCP에 접근 가능해짐 (보안 사고).

### 4.2 GitHub Secrets/Variables 6종 신규 등록 (담당자 = repo admin)

**전부 신규** (재사용 가능한 기존 값 없음 — `gh api .../actions/secrets` total_count: 0 확인됨):

| 이름 | 종류 | 값 |
|---|---|---|
| `GCP_WIF_PROVIDER` | Secret | §4.1 #2의 provider full resource name (`projects/<num>/locations/global/workloadIdentityPools/github-actions/providers/github`) |
| `GCP_WIF_SERVICE_ACCOUNT` | Secret | `<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com` |
| `GCP_PROJECT_ID_PROD` | Variable | `<GCP_PROJECT_ID>` (이름이 `_PROD`지만 staging도 같은 project 공용) |
| `GCP_REGION` | Variable | `asia-northeast3` |
| `MODAL_TOKEN_ID` | Secret | 담당자 보유 |
| `MODAL_TOKEN_SECRET` | Secret | 담당자 보유 |

값에 trailing whitespace/개행 들어가면 `gcloud` 명령어가 "invalid reference format"으로 fail. 등록 시 trim 주의.

### 4.3 Modal 토큰 발급 확인

`modal token current` 명령어로 출력되는 workspace가 `dhwang0803`인지 확인. 다른 워크스페이스면 sub-agent 간 RPC 깨짐.

---

## 5. 왜 굳이 지금 해야 하나

### 5.1 발표 덱 신뢰도 — 가장 큰 이유
PART 04에 "Ruff/TS/pytest 3중 자동 차단 + Cloud Run 자동 배포 + Modal 자동 배포 가능합니다"라고 명시했는데 **실제로는 다 거짓말**. 데모 도중 누가 `.github/workflows/` 열어보면 발각됨. **데모 D-3까지 진짜로 만드는 게 본 작업의 1차 목적.**

### 5.2 누적된 사고 패턴 차단
실제 기록된 것만:
- composer 5/26 코드 머지 후 배포 잊음 → 다음 배포 때 surprise crash
- OAuth redirect-uri 5/27 secret 변경 후 Console 동기화 잊음 → 8일간 SSO 깨진 채

자동화하면 "머지하면 배포까지 자동"이라 사람이 잊을 단계가 줄어든다.

### 5.3 브랜치 보호 효력 발생 조건
GitHub Branch Protection의 "required status checks"는 **실제 돌아가는 워크플로우 이름**을 등록해야 동작. ruff/pytest 워크플로우가 없으면 branch protection을 설정해도 등록할 게 없음. 본 PR로 워크플로우가 생긴 다음에야 비로소 branch protection이 실효성을 가진다.

---

## 6. 후속 작업 (Deferred — 작업 계획서 §10)

본 PR scope 밖. 데모 끝나고 영구 운영 진입 시.

| 항목 | 왜 후속인가 |
|---|---|
| **prod 환경 신설** | 본 프로젝트는 7/1 destroy 예정이라 prod 안 만듦. 영구 운영 결정 시 만들어야 함 |
| **`lifecycle.ignore_changes = [image]` terraform 추가** | `gcloud run services update`로 image 교체 후 다음 `terraform apply` 시 image가 stale tfvars로 revert될 위험. 영구 운영하려면 필수 |
| **`ruff format .` 1회 정리** | 현재 codebase가 format strict 아님. 본 PR에서 format strict 켜면 대규모 diff 발생 위험 → 별도 PR로 분리 |
| **frontend ESLint/tsc 클린업** | 마찬가지로 첫 실행에서 fail 가능. 임시 우회 후 후속 정리 |
| **pre-commit hook** | 로컬에서 ruff 사전 차단해 push 후 CI 실패 사이클 단축. 편의 기능이라 후순위 |
| **Slack/Discord 알림** | 배포 결과 채널 알림. 컨벤션 없어서 보류 |
| **`actionlint`** | 워크플로우 yml 자체의 정확성을 메타 검증. 안정화 후 |

---

## 7. 담당자가 받았을 때 헷갈릴 부분 미리 짚기

작업 계획서가 두꺼워서 헷갈릴 만한 곳.

1. **"왜 staging만 만들고 prod은 안 만드나"** → 본 프로젝트는 7/1 destroy 예정. prod Cloud Run 0건. 영구 운영이 아니라 데모용 인프라
2. **"WIF SA 신규 발급?"** → **YES. 전부 신규.** 작업 계획서 초안은 "옵션 B (기존 prod SA 재사용)"였으나 실측 결과 본 프로젝트에 WIF 0개·Secrets 0개 — 재사용할 게 없음. §4.1의 6단계로 처음부터 셋업. 약 60~90분 소요
3. **"`GCP_PROJECT_ID_PROD`인데 왜 staging에서도 쓰나"** → variable 이름은 prod지만 실제 값은 staging도 같은 project. 이름이 misleading함. variable rename은 후속 작업
4. **"`deploy-prod.yml` 왜 삭제하나"** → 다른 프로젝트(`auto-workflow`) 가리키는 stale 코드. 본 repo에 잘못 commit된 흔적. release 트리거 충돌 자동 해소 효과도 있음. **+ 부수 의미**: 이 yml이 한 번도 실행된 적 없다는 게 prod WIF가 셋업된 적 없는 증거 — §2 (WIF) 신규 셋업 결정의 근거
5. **"ruff format 빨간색 뜨면?"** → 본 PR scope 밖 (§10 후속). 본 step만 `continue-on-error: true`로 임시 우회 또는 step 제거
6. **"테스트 0개인데 jest가 fail하면?"** → `--passWithNoTests`로 safety net 걸어둠
7. **"WIF attribute-condition 왜 필요한가"** → 누락 시 임의 GitHub repo가 우리 GCP에 접근 가능해짐. `assertion.repository=='billionaireahreum/Workflow_Automation'` 조건이 본 repo의 actions만 허용하는 보안 게이트 (§4.1 #2)

---

## 8. 정리 — 본 작업의 그림

```
[지금]                              [본 작업 후]
손으로 ruff 돌림           →  PR 올리면 자동 ruff 검사 + fail 시 머지 차단
손으로 pytest 돌림         →  PR 올리면 자동 pytest (PG 컨테이너 포함)
손으로 gcloud builds submit →  release 머지하면 자동 build + Cloud Run 갱신
손으로 modal deploy         →  release 머지하면 변경된 Modal app만 자동 재배포
deploy-prod.yml (stale)    →  삭제
```

**1 PR로 4개 워크플로우 신설 + 1개 삭제. 담당자 1명, 마감 5/31.**

---

## 9. 더 깊이 알고 싶다면

- **WIF 동작 원리**: GCP 공식 문서 "Workload Identity Federation with GitHub Actions". 본 입문서 §2.4의 5요소(Pool/Provider/SA/role grant/impersonate)는 거기서 가져온 골격. 본 프로젝트는 처음부터 셋업이므로 6단계 실행 명령어가 작업 계획서 §4.1에 박혀있음
- **Cloud Build vs `docker build`**: Cloud Build는 GCP가 호스팅하는 빌드 서버. `cloudbuild.yaml`로 빌드 절차 선언. 로컬 docker 불필요. 본 프로젝트는 monorepo build context가 repo root라 Cloud Build 패턴으로 통일
- **paths-filter**: 변경된 파일 경로만 보고 어떤 job을 실행할지 결정. 예) `services/frontend/**` 변경 시 frontend deploy job만 실행, api_server job은 skip
- **service container (GitHub Actions)**: yml의 `services:` 블록으로 PG/Redis 등을 컨테이너로 띄움. 테스트 끝나면 자동 정리

---

## 관련 문서

- [ci-cd-automation-plan.md](./ci-cd-automation-plan.md) — 본 입문서 기반의 실제 작업 계획서 (담당자 직접 입력용)
