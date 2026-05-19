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
  description = "IAM principals allowed to read all agent secrets"
  type        = list(string)
  default = [
    # Modal app boot에서 secret pull하는 공용 SA
    "serviceAccount:<MODAL_SA>@<GCP_PROJECT_ID>.iam.gserviceaccount.com",
    # 팀원 5명 (조장 + sub-agent 담당자 4명)
    "user:<TEAM_MEMBER_1>@example.com",
    "user:dhwang0803@gmail.com",
    "user:<TEAM_MEMBER_2>@example.com",
    "user:<TEAM_MEMBER_3>@example.com",
    "user:<TEAM_MEMBER_4>@example.com",
  ]
}
