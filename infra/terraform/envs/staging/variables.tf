variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "staging"
}

variable "vpc_name" {
  description = "VPC base name (suffix '-{env}' appended by module)"
  type        = string
  default     = "workflow-vpc"
}

# ---------------------------------------------------------------------------
# Secret Manager (existing PR #80)
# ---------------------------------------------------------------------------
variable "agent_secret_names" {
  description = "Modal sub-agent secret IDs managed in GCP Secret Manager"
  type        = list(string)
  default = [
    # Cloud SQL IAM 공통 (composer / personalization / skills-builder)
    "cloud-sql-instance",
    "db-iam-user",
    "db-name",
    # LLM base endpoints (3 sub-agent 공통)
    "llm-base-url",
    "embedding-base-url",
    # personalization 전용
    "gcs-personal-bucket",
    # orchestrator → sub-agent 라우팅
    "composer-url",
    "skills-builder-url",
    "personalization-url",
    # llm-base 전용
    "huggingface-token",
    # execution_engine Celery broker + api_server SSE pub/sub (REQ-007/009, PR #84 후속)
    "redis-url",
    # api_server 전용 (REQ-009, PR #75 Cloud Run 배포 — 본 PR-C 추가)
    "jwt-secret-key",       # JWT 토큰 서명 키 (32바이트+)
    "encryption-key",       # AES-GCM 암호화 키 (base64 32바이트)
    "google-client-id",     # Google OAuth Client ID
    "google-client-secret", # Google OAuth Client Secret
    "google-redirect-uri",  # OAuth callback URL (staging Cloud Run public hostname)
  ]
}

variable "agent_secret_accessors" {
  description = "IAM principals allowed to read all agent secrets + write to personal-memory bucket"
  type        = list(string)
  default = [
    # Modal app boot에서 secret pull + GCS write하는 공용 SA
    "serviceAccount:<MODAL_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com",
    # 팀원 5명 (조장 + sub-agent 담당자 4명)
    "user:<TEAM_MEMBER_1>@example.com",
    "user:dhwang0803@gmail.com",
    "user:<TEAM_MEMBER_2>@example.com",
    "user:<TEAM_MEMBER_3>@example.com",
    "user:<TEAM_MEMBER_4>@example.com",
  ]
}

# ---------------------------------------------------------------------------
# Cloud SQL — staging은 manual workflow-dev 유지 (default false)
# 신규 인스턴스 필요 시 true로 활성화
# ---------------------------------------------------------------------------
variable "enable_cloud_sql" {
  description = "Create new Cloud SQL instance via terraform (staging default false — manual workflow-dev maintained)"
  type        = bool
  default     = false
}

variable "cloud_sql_iam_users" {
  description = "Cloud SQL IAM users to register (when enable_cloud_sql=true)"
  type        = list(string)
  default     = []
}

# ---------------------------------------------------------------------------
# Cloud Run — REQ-009 api_server (default false — 이미지 빌드 완료 시 활성화)
# ---------------------------------------------------------------------------
variable "enable_cloud_run" {
  description = "Deploy api_server to Cloud Run (default false — Modal sub-agent 운영 중)"
  type        = bool
  default     = false
}

variable "api_server_image" {
  description = "api_server container image (gcr.io/PROJECT/api-server:TAG). Required when enable_cloud_run=true"
  type        = string
  default     = ""
}

variable "api_server_service_account" {
  description = "Runtime service account email for api_server Cloud Run"
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Cloud Run — REQ-007 execution_engine worker (Celery worker daemon)
# 패턴 옵션 A: Cloud Run service + dummy HTTP probe + celery subprocess.
# Worker entry는 services/execution_engine/src/worker_entry.py.
# ---------------------------------------------------------------------------
variable "enable_execution_engine_worker" {
  description = "Deploy execution_engine Celery worker to Cloud Run (default false — 이미지 빌드 완료 + Redis 가용 시 활성화)"
  type        = bool
  default     = false
}

variable "execution_engine_worker_image" {
  description = "execution_engine worker container image (gcr.io/PROJECT/execution-engine-worker:TAG). Required when enable_execution_engine_worker=true"
  type        = string
  default     = ""
}

variable "execution_engine_worker_service_account" {
  description = "Runtime service account email for execution_engine worker. 권한: Cloud SQL IAM Authenticator + VPC-SC(Redis Private Service Access) + Secret Manager secretAccessor (본 PR locals.effective_secret_accessors가 자동 부여). SA 자체 생성은 현재 gcloud로 수동 — 후속 PR에서 google_service_account 리소스로 코드화 예정"
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Artifact Registry image push 권한자 — Cloud Build CI / 팀원 gcloud builds submit.
# 기본값이 빈 list면 agent_secret_accessors fallback (현 staging 운영 패턴).
# CI SA를 별도로 두거나 비-팀원 contractor가 추가될 때 본 변수만 명시 override.
# ---------------------------------------------------------------------------
variable "artifact_registry_writers" {
  description = "Artifact Registry writer IAM principals (image push). 빈 list면 agent_secret_accessors fallback"
  type        = list(string)
  default     = []
}

# ---------------------------------------------------------------------------
# Cloud Run — REQ-010 frontend (Next.js). 단일 출처 토폴로지(A):
# 프론트가 public 진입점이고 next.config rewrites가 /api/* 를 api_server로 프록시.
# enable_cloud_run=true 전제 (API_PROXY_TARGET이 api_server URL을 참조).
# ---------------------------------------------------------------------------
variable "enable_frontend" {
  description = "Deploy frontend to Cloud Run (default false — 이미지 빌드 완료 시 활성화). enable_cloud_run=true 전제."
  type        = bool
  default     = false
}

variable "frontend_image" {
  description = "frontend container image (AR 경로:TAG). Required when enable_frontend=true"
  type        = string
  default     = ""
}

variable "frontend_service_account" {
  description = "Runtime service account email for frontend Cloud Run. 프론트는 secret/DB 미사용 — staging은 공용 SA 재활용 가능"
  type        = string
  default     = ""
}

variable "frontend_url" {
  description = "배포된 frontend Cloud Run URL. api_server FRONTEND_URL(OAuth 콜백 후 302 대상)에 주입. 2단계 apply — 프론트 배포 후 채운다."
  type        = string
  default     = ""
}
