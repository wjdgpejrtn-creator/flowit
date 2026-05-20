project_id  = "<GCP_PROJECT_ID>"
region      = "asia-northeast3"
environment = "staging"

# ---------------------------------------------------------------------------
# Cloud Run 배포 — Phase F 풀스택 smoke 완료 시점 staging 상태 (2026-05-20)
# 이 파일은 git 추적됨 (.gitignore 예외) — apply를 -var 없이 해도 drift 없도록 영속화.
# 이미지 tag 갱신 시 이 파일도 함께 commit.
# ---------------------------------------------------------------------------
enable_cloud_run               = true
enable_execution_engine_worker = true

api_server_image              = "asia-northeast3-docker.pkg.dev/<GCP_PROJECT_ID>/<AR_REPO>/api-server:phase-f-5"
execution_engine_worker_image = "asia-northeast3-docker.pkg.dev/<GCP_PROJECT_ID>/<AR_REPO>/execution-engine-worker:phase-f-5"

# staging은 공용 SA 재활용 ([[sub_agent_cloud_sql_iam]] — Cloud SQL IAM + Secret Manager 권한 보유).
# production 이관 시 서비스별 SA 분리.
api_server_service_account              = "<MODAL_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com"
execution_engine_worker_service_account = "<MODAL_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com"
