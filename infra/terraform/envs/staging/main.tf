terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "workflow-auto-tfstate"
    prefix = "staging"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  common_labels = {
    environment = var.environment
    managed_by  = "terraform"
    req         = "req-011-infra"
  }
}

# ---------------------------------------------------------------------------
# Networking — VPC + Subnet + Serverless connector + Cloud SQL/Memorystore peering
# Prerequisite for cloud-sql / memorystore / cloud-run (private IP egress)
# ---------------------------------------------------------------------------
module "networking" {
  source = "../../modules/networking"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment
  vpc_name    = var.vpc_name
}

# ---------------------------------------------------------------------------
# Required project services for Cloud Run image build + deploy
# (Artifact Registry는 이미 enabled. Cloud Build는 staging 신규 enable.)
# ---------------------------------------------------------------------------
resource "google_project_service" "cloudbuild" {
  project            = var.project_id
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run" {
  project            = var.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

# Cloud Build default compute SA — 기본 권한 부족 사례 (소스 업로드용 GCS object get
# + Cloud Logging write + Artifact Registry write). gcloud builds submit 시 필요.
data "google_project" "this" {
  project_id = var.project_id
}

locals {
  cloud_build_default_sa = "serviceAccount:${data.google_project.this.number}-compute@developer.gserviceaccount.com"
  cloud_build_sa_roles = toset([
    "roles/storage.objectAdmin",     # 소스 tarball get/put (gs://PROJECT_cloudbuild/...)
    "roles/logging.logWriter",       # CLOUD_LOGGING_ONLY 옵션 사용 시
    "roles/artifactregistry.writer", # docker push to AR repo
  ])
}

resource "google_project_iam_member" "cloud_build_default_sa" {
  for_each = local.cloud_build_sa_roles
  project  = var.project_id
  role     = each.value
  member   = local.cloud_build_default_sa

  depends_on = [google_project_service.cloudbuild]
}

# ---------------------------------------------------------------------------
# Artifact Registry — Cloud Run service 이미지 저장소 (api_server + execution_engine worker)
# ---------------------------------------------------------------------------
module "container_registry" {
  source = "../../modules/artifact-registry"

  project_id    = var.project_id
  location      = var.region
  repository_id = "workflow-${var.environment}"
  format        = "DOCKER"
  description   = "Cloud Run images for api_server + execution_engine worker (REQ-009/REQ-007 staging)"

  reader_members = compact([
    var.api_server_service_account != "" ? "serviceAccount:${var.api_server_service_account}" : "",
    var.execution_engine_worker_service_account != "" ? "serviceAccount:${var.execution_engine_worker_service_account}" : "",
  ])
  writer_members = var.agent_secret_accessors # 팀원이 gcloud builds submit 시 push 권한 필요

  labels = merge(local.common_labels, { role = "container-registry" })
}

# ---------------------------------------------------------------------------
# Secret Manager — 11 sub-agent secrets (Modal pull, ADR-0014 후속 PR #80)
# ---------------------------------------------------------------------------
module "agent_secrets" {
  source = "../../modules/secret-manager"

  project_id       = var.project_id
  secret_names     = var.agent_secret_names
  accessor_members = var.agent_secret_accessors
}

# ---------------------------------------------------------------------------
# GCS — personalization PersonalMemoryStore bucket (ADR-0014 § Personal Memory)
# REQ-004 personalization sub-agent + 사용자별 memory.md (PR #76 본문 "5/25 예정")
# ---------------------------------------------------------------------------
module "personal_memory_bucket" {
  source = "../../modules/gcs"

  project_id    = var.project_id
  location      = var.region
  bucket_name   = "${var.project_id}-personal-memory-${var.environment}"
  storage_class = "STANDARD"
  force_destroy = true # staging only

  writer_members = var.agent_secret_accessors # SA + team members (write/read 둘 다 필요)
  reader_members = []

  labels = merge(local.common_labels, { role = "personal-memory" })
}

# ---------------------------------------------------------------------------
# Memorystore (Redis) — execution_engine Celery broker + api_server SSE pub/sub
# REQ-007/009 (ADR-0015 §F2-2 후속 호출 경로 B 트리거)
# ---------------------------------------------------------------------------
module "redis" {
  source = "../../modules/memorystore"

  project_id         = var.project_id
  region             = var.region
  environment        = var.environment
  tier               = "BASIC"
  memory_size_gb     = 1
  authorized_network = module.networking.vpc_self_link

  labels = merge(local.common_labels, { role = "celery-broker" })

  depends_on = [module.networking]
}

# ---------------------------------------------------------------------------
# Cloud SQL — staging은 기존 manual 인스턴스(workflow-dev) 유지 (terraform import 미반영)
# 신규 인스턴스가 필요하면 var.enable_cloud_sql = true로 활성화
# ---------------------------------------------------------------------------
module "cloud_sql" {
  count  = var.enable_cloud_sql ? 1 : 0
  source = "../../modules/cloud-sql"

  project_id                    = var.project_id
  region                        = var.region
  instance_name                 = "workflow-${var.environment}"
  database_version              = "POSTGRES_16"
  tier                          = "db-f1-micro"
  availability_type             = "ZONAL"
  private_network               = module.networking.vpc_self_link
  service_networking_connection = module.networking.private_vpc_connection
  iam_users                     = var.cloud_sql_iam_users
  deletion_protection           = false # staging
  labels                        = merge(local.common_labels, { role = "primary-db" })
}

# ---------------------------------------------------------------------------
# Cloud Run — api_server (REQ-009) 배포 슬롯. 이미지 빌드 완료 시 활성화
# var.enable_cloud_run = true + var.api_server_image 지정으로 활성화
# ---------------------------------------------------------------------------
module "api_server" {
  count  = var.enable_cloud_run ? 1 : 0
  source = "../../modules/cloud-run"

  project_id            = var.project_id
  region                = var.region
  service_name          = "workflow-api-${var.environment}"
  image                 = var.api_server_image
  service_account_email = var.api_server_service_account
  vpc_connector_id      = module.networking.serverless_connector_id
  vpc_egress            = "PRIVATE_RANGES_ONLY"
  cpu                   = "1"
  memory                = "1Gi"
  min_instances         = 0
  max_instances         = 5
  container_port        = 8080
  allow_public_access   = true # staging — Cloud IAP 미적용 시 public
  ingress               = "INGRESS_TRAFFIC_ALL"
  cpu_idle              = true # api_server는 request 기반 — request 없을 때 CPU 할당 안 함 (기본)

  env_vars = {
    ENVIRONMENT = var.environment
    REDIS_URL   = module.redis.redis_url
  }

  labels = merge(local.common_labels, { role = "api-server" })

  depends_on = [module.networking, module.redis]
}

# ---------------------------------------------------------------------------
# Cloud Run — REQ-007 execution_engine worker (Celery worker daemon)
# 옵션 A: Cloud Run service + dummy HTTP probe + celery worker subprocess.
# - min/max=1: 단일 worker 인스턴스 (큐 깊이 기반 스케일링은 후속)
# - cpu_idle=false: long-running celery process이므로 always-on CPU
# - ingress=INTERNAL_ONLY: 외부 HTTP 접근 차단 (health-check만)
# - allow_public_access=false: VPC 내부에서만 접근 가능
# ---------------------------------------------------------------------------
module "execution_engine_worker" {
  count  = var.enable_execution_engine_worker ? 1 : 0
  source = "../../modules/cloud-run"

  project_id            = var.project_id
  region                = var.region
  service_name          = "workflow-execution-worker-${var.environment}"
  image                 = var.execution_engine_worker_image
  service_account_email = var.execution_engine_worker_service_account
  vpc_connector_id      = module.networking.serverless_connector_id
  vpc_egress            = "PRIVATE_RANGES_ONLY"
  cpu                   = "1"
  memory                = "1Gi"
  min_instances         = 1
  max_instances         = 1
  container_port        = 8080
  allow_public_access   = false
  ingress               = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  cpu_idle              = false # Celery worker는 long-running daemon — request idle 없음

  env_vars = {
    ENVIRONMENT = var.environment
    REDIS_URL   = module.redis.redis_url
  }

  labels = merge(local.common_labels, { role = "execution-worker" })

  depends_on = [module.networking, module.redis]
}
