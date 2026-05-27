project_id  = "<GCP_PROJECT_ID>"
region      = "asia-northeast3"
environment = "staging"

# ---------------------------------------------------------------------------
# Cloud Run 배포 — Phase F 풀스택 smoke 완료 시점 staging 상태 (2026-05-20)
# 이 파일은 git 추적됨 (.gitignore 예외) — apply를 -var 없이 해도 drift 없도록 영속화.
# 이미지 tag 갱신 시 이 파일도 함께 commit.
#
# ⚠️ 비밀값 추가 금지 — 이 파일은 `*.tfvars` gitignore 예외라 commit 시 자동 추적·push된다.
#    DB 비밀번호 / API 토큰 / SA 키 등은 절대 넣지 말 것. GCP Secret Manager 경유.
#    허용: image tag, SA email(식별자), bool, project_id/region 같은 비-비밀 식별자만.
# ---------------------------------------------------------------------------
enable_cloud_run               = true
enable_execution_engine_worker = true

api_server_image              = "asia-northeast3-docker.pkg.dev/<GCP_PROJECT_ID>/<AR_REPO>/api-server:phase-f-6"
execution_engine_worker_image = "asia-northeast3-docker.pkg.dev/<GCP_PROJECT_ID>/<AR_REPO>/execution-engine-worker:adr-0018-2b"

# api_server / worker 모두 dedicated SA (PR-A/B 2-PR 패턴으로 공용 cloudsql-iam-modal에서 분리, 격리).
# 공용 cloudsql-iam-modal은 Modal sub-agents 3종(skills_builder/composer/personalization) 전용으로 축소.
api_server_service_account              = "<API_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com"
execution_engine_worker_service_account = "<WORKER_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com"
