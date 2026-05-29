# CI/CD 자동화 인계 — 박아름 ↔ 황대원 Q&A

**일자**: 2026-05-29
**문의자**: 박아름 (CI/CD 작업 담당자)
**답변자**: 황대원 (조장)
**관련 문서**: [ci-cd-automation-plan.md](./ci-cd-automation-plan.md) · [ci-cd-explained.md](./ci-cd-explained.md)

---

## 배경

작업 계획서 v1 초안은 "옵션 B (기존 prod WIF SA 재사용)"를 가정했으나, 박아름님이 사전 확인 중 본 프로젝트(`<GCP_PROJECT_ID>`)에 WIF가 셋업된 적 없음을 발견. 본 문서는 후속 Q&A 정리.

황대원이 §4.1 6단계 GCP WIF 신규 셋업을 실행 완료(2026-05-29) → 박아름은 §4.2 GitHub Settings 등록만 진행하면 됨.

---

## #2 — GitHub Secrets / Variables 6종 신규 등록 값

**전부 신규** (재사용 가능한 기존 값 없음 — `gh api .../actions/secrets` total_count: 0 확인).

| 이름 | 종류 | 값 |
|---|---|---|
| `GCP_WIF_PROVIDER` | Secret | `projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/github-actions/providers/github` |
| `GCP_WIF_SERVICE_ACCOUNT` | Secret | `<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com` |
| `GCP_PROJECT_ID_PROD` | Variable | `<GCP_PROJECT_ID>` |
| `GCP_REGION` | Variable | `asia-northeast3` |
| `MODAL_TOKEN_ID` | Secret | (박아름 보유 Modal 토큰) |
| `MODAL_TOKEN_SECRET` | Secret | (박아름 보유 Modal 토큰) |

**주의**: GitHub UI에서 복붙 시 trailing whitespace/개행 들어가면 `gcloud` 명령어가 "invalid reference format"으로 fail (`deploy-prod.yml`의 `Validate inputs` step이 이미 이런 사고 1회 경험 — 2026-04-19 `GCP_REGION` 끝 공백 사고). trim 확인.

---

## #3 — SA 5종 role grant 검증 (황대원이 확인 완료)

박아름님 GCP 계정(`army5833`)은 `<GCP_PROJECT_ID>` IAM 권한 없어 콘솔 확인 불가 → 황대원이 대신 검증.

**검증 명령**:
```bash
gcloud projects get-iam-policy <GCP_PROJECT_ID> \
  --flatten="bindings[].members" \
  --filter="bindings.members:<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com" \
  --format="value(bindings.role)"
```

**결과** (2026-05-29 재검증):
```
roles/artifactregistry.writer
roles/cloudbuild.builds.builder
roles/iam.serviceAccountUser
roles/run.admin
roles/storage.objectAdmin
```

5종 전부 **project-level** grant ✅. 추가 작업 없음.

---

## #4 — Modal 사전 셋업 상태 (가정 일부 정정)

박아름님 가정과 실제 아키텍처가 다른 부분 있음. 항목별로:

| 항목 | 박아름 가정 | 실제 | 액션 |
|---|---|---|---|
| `cloudsql-iam-sa` Modal secret | 존재해야 함 | ✅ 존재 (`Last used: 2026-05-29 10:37`, 오늘도 사용 중) | 없음 |
| "agent별 secret 5종 (`agent-composer-secret` 등)" | 5종 필요 | ⚠️ **그 naming은 없음** — 실제 아키텍처는 다름 (아래 §4.1) | naming 정정 |
| llm-base Volume backfill — Gemma 4 | 필요 | ✅ 완료 (`llm-base-models` Volume에 `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf` 16.9 GiB + `mmproj-F16.gguf`) | 없음 |
| llm-base Volume backfill — BGE-M3 | 필요 | ⚠️ **Volume에 없음** — cold start마다 HF에서 download (실행은 정상) | 데모 후 백필 검토 |

### #4.1 실제 Modal/GCP secret 아키텍처 (박아름 가정 정정)

박아름님이 가정한 `agent-composer-secret / agent-orchestrator-secret / agent-skills-builder-secret / agent-personalization-secret / agent-llm-base-secret` 5종 naming은 **양쪽 어디에도 없음**. 실제는:

#### Modal secrets (5종 — `dhwang0803` workspace)

| 이름 | 용도 |
|---|---|
| `cloudsql-iam-sa` | DB IAM 인증용 SA JSON (5 agent 공유) |
| `agent-bearer-token` | agent ↔ agent RPC bearer 토큰 (공유) |
| `agent-personalization-secret` | personalization 전용 (legacy) |
| `huggingface-token` | llm-base가 BGE-M3 등 모델 download 시 사용 |
| `langsmith-api-key` | LangSmith trace |

검증 명령: `modal secret list --json`

#### GCP Secret Manager (`<GCP_PROJECT_ID>`) — 5 agent URL은 여기

| 카테고리 | secret 이름 |
|---|---|
| Agent URL (5) | `composer-url`, `llm-base-url`, `orchestrator-url`, `personalization-url`, `skills-builder-url` |
| DB | `db-iam-user`, `db-iam-user-api`, `db-iam-user-worker`, `cloud-sql-instance`, `db-name` |
| OAuth | `google-client-id`, `google-client-secret`, `google-redirect-uri` |
| Auth | `jwt-secret-key`, `encryption-key` |
| GCS 버킷 | `gcs-personal-bucket`, `gcs-session-bucket`, `skills-marketplace-bucket` |
| 기타 | `redis-url`, `embedding-base-url`, `huggingface-token` (Modal과 중복 — 의도) |

검증 명령: `gcloud secrets list --project=<GCP_PROJECT_ID>`

#### modal-deploy.yml에 미치는 영향

- **modal-deploy.yml은 secret을 생성하지 않음**. 기존 secret이 `main.py`의 `modal.Secret.from_name(...)` 선언으로 deploy 시 자동 mount됨
- 박아름님은 modal-deploy.yml 작성 시 secret 관련 step 0건 추가 — **순수히 `modal deploy services/agents/<app>/main.py` 호출만**

### #4.2 5 agent 배포 상태 (modal-deploy.yml은 갈아끼우기 작업)

`modal app list --json` 결과:

| App | State | Tasks | Created |
|---|---|---|---|
| `agent-skills-builder` | deployed | 1 | 2026-05-26 |
| `llm-base` | deployed | 1 | 2026-05-26 |
| `agent-personalization` | deployed | 1 | 2026-05-28 |
| `agent-composer` | deployed | 0 | 2026-05-28 |
| `orchestrator` | deployed | 1 | 2026-05-28 |

전부 `dhwang0803` workspace에 정상 배포 → modal-deploy.yml은 **first deploy 아니라 갈아끼우기**. 작업 부담 낮음.

### #4.3 BGE-M3 Volume 미백필 — 데모 영향도

`SentenceTransformer("BAAI/bge-m3")`가 첫 cold start마다 HuggingFace에서 ~2 GB 다운로드. 운영상:
- **데모 D-3 영향**: 없음. llm-base가 이미 `Tasks: 1`로 warm. 데모 시연 중 cold start 발생할 가능성 낮음
- **장기 영향**: cold start +2~3분. 영구 운영 시 Volume에 백필 권장 (현 프로젝트는 7/1 destroy 예정이라 후순위)

데모 후 Volume에 BGE-M3 caching하려면 `main.py`의 SentenceTransformer 호출에 `cache_folder=MODEL_DIR/bge-m3-cache` 명시 + `download_model` 함수에 BGE-M3 백필 추가 필요. 별도 작업.

---

## #1 — 종결 (미발신)

박아름님 메시지에 #1 항목 미발신 — 본 문서 작성 시점 기준 추가 문의 없음. 별도 갱신 불필요.

---

## 박아름 다음 액션 정리

### 즉시 (오늘)
- [ ] §2 표의 6종 GitHub Secrets/Variables 등록 (repo admin 권한)
  - Secret 4종: `GCP_WIF_PROVIDER`, `GCP_WIF_SERVICE_ACCOUNT`, `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`
  - Variable 2종: `GCP_PROJECT_ID_PROD`, `GCP_REGION`
- [ ] Modal 토큰 발급 + `modal token current` username = `dhwang0803` 확인 (다른 워크스페이스면 sub-agent RPC 깨짐)

### PR 작업 (D-3 마감, 5/31)
- [ ] 4 workflow yml 작성 ([ci-cd-automation-plan.md §3](./ci-cd-automation-plan.md) 골격 그대로)
- [ ] `deploy-prod.yml` 삭제 (stale 코드)
- [ ] 로컬 검증 ([§5.1](./ci-cd-automation-plan.md))
- [ ] PR open → ruff/pytest CI 통과 확인 → development 머지

### PR 머지 후
- [ ] release FF 머지로 첫 배포 trigger
- [ ] §5.4 검증 (staging Cloud Run + Modal 5 agent revision 갱신 확인)
- [ ] Branch protection rules 등록 ([§4.5](./ci-cd-automation-plan.md))

---

## 황대원 측 완료 사항

- [x] GCP WIF 신규 셋업 6단계 ([§4.1](./ci-cd-automation-plan.md)) — 2026-05-29
  - WIF Pool `github-actions`
  - WIF Provider `github` (OIDC + attribute-condition `assertion.repository=='billionaireahreum/Workflow_Automation'`)
  - Deploy SA `<CICD_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com`
  - 5종 IAM role grant
  - WIF → SA impersonate 바인딩
  - 셋업 검증 (provider + SA roles)
- [x] §3 박아름 문의 #3 검증 (5종 role 다 grant됨)
- [x] §4 박아름 문의 #4 Modal 상태 직접 확인 (5 agent 배포 + Volume 상태)
- [x] [작업 계획서](./ci-cd-automation-plan.md) §2/§4/§6/§8/§9/§11 동기화 (옵션 B 폐기, 신규 셋업 절차 반영)
- [x] [입문서](./ci-cd-explained.md) §2.4/§4/§7 동기화

---

## 문의 / 의사결정

- WIF 셋업 추가 IAM 작업 필요 시: 황대원 (`<GCP_PROJECT_ID>` IAM admin)
- modal-deploy.yml 변경 / Modal app naming 충돌: 황대원 (Modal workspace owner)
- 본 문서 의사결정 책임: 황대원 (조장)
