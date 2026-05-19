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
