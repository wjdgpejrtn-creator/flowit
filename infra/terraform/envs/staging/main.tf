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

  # Cloud Build SA가 GCS bucket source upload / Cloud Logging write / AR push에
  # 필요한 권한 — 이름 부여 (line 22+ data.google_project.this 정의 이후 사용)
  # AR push 권한자 — 명시적 override 없으면 secret accessor list 재사용 (현 staging 운영 패턴).
  # 별도 CI SA가 추가될 때 var.artifact_registry_writers를 채워 의미 분리.
  ar_writers = length(var.artifact_registry_writers) > 0 ? var.artifact_registry_writers : var.agent_secret_accessors

  # GCP Secret Manager `secretAccessor` 멤버 — 기존 5명/Modal SA + Cloud Run SA(설정된 경우).
  # api_server / worker SA가 같은 공용 SA(cloudsql-iam-modal)를 재활용할 수 있으므로 distinct()
  # 처리 — for_each duplicate key 방지.
  effective_secret_accessors = distinct(compact(concat(
    var.agent_secret_accessors,
    var.api_server_service_account != "" ? ["serviceAccount:${var.api_server_service_account}"] : [],
    var.execution_engine_worker_service_account != "" ? ["serviceAccount:${var.execution_engine_worker_service_account}"] : [],
  )))
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

  reader_members = compact(concat(
    [
      var.api_server_service_account != "" ? "serviceAccount:${var.api_server_service_account}" : "",
      var.execution_engine_worker_service_account != "" ? "serviceAccount:${var.execution_engine_worker_service_account}" : "",
    ],
    # frontend 런타임 SA — 자기 이미지 pull용 AR reader (enable_frontend 시에만)
    [for e in google_service_account.frontend[*].email : "serviceAccount:${e}"],
  ))
  writer_members = local.ar_writers # default = agent_secret_accessors fallback (var.artifact_registry_writers override 가능)

  labels = merge(local.common_labels, { role = "container-registry" })
}

# ---------------------------------------------------------------------------
# Secret Manager — 11 sub-agent secrets (Modal pull, ADR-0014 후속 PR #80)
# ---------------------------------------------------------------------------
module "agent_secrets" {
  source = "../../modules/secret-manager"

  project_id       = var.project_id
  secret_names     = var.agent_secret_names
  accessor_members = local.effective_secret_accessors
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
# GCS — skills marketplace SkillDocument bucket (ADR-0017 이중 저장 "지침서" 측)
# api_server가 SkillDocumentStore(skills_marketplace Port) DI로 read/write.
# 일반 업로드 GCS_BUCKET_NAME과 분리 — 스킬 문서가 일반 파일과 같은 버킷에 섞이지 않도록.
# 키 패턴: gs://{bucket}/skills/{skill_id}/SKILL.md
# ---------------------------------------------------------------------------
module "skills_marketplace_bucket" {
  source = "../../modules/gcs"

  project_id    = var.project_id
  location      = var.region
  bucket_name   = "${var.project_id}-skills-marketplace-${var.environment}"
  storage_class = "STANDARD"
  force_destroy = true # staging only

  # api_server SA + 팀 — api_server가 consumer(SkillDocumentStore DI factory),
  # 팀원은 debugging/seed 용도. personal_memory와 달리 api_server SA를 명시적 포함.
  writer_members = distinct(concat(
    var.agent_secret_accessors,
    var.api_server_service_account != "" ? ["serviceAccount:${var.api_server_service_account}"] : [],
  ))
  reader_members = []

  labels = merge(local.common_labels, { role = "skills-marketplace" })
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
# api_server 전용 Cloud Run runtime SA — 공용 cloudsql-iam-modal에서 분리 (격리, PR-A 준비).
# 본 PR(1단계, prep)은 SA 생성 + project IAM grant만 — Cloud Run 미전환 (tfvars 미변경).
# 후속 PR(2단계, switch)에서 Cloud SQL IAM user 추가 + DB GRANT(수동) + db-iam-user
# secret 갱신 + api_server_service_account tfvars → 본 SA 이메일로 전환 + Cloud Run
# revision 재배포. 메모리 staging_db_state §"PG 16/IAM 함정 8종" 절차 적용 필요.
# ---------------------------------------------------------------------------
resource "google_service_account" "api_server" {
  count        = var.enable_cloud_run ? 1 : 0
  project      = var.project_id
  account_id   = "workflow-api-${var.environment}-sa"
  display_name = "REQ-009 api_server Cloud Run runtime SA (least privilege, 공용 cloudsql-iam-modal 대체)"
}

# Cloud SQL IAM auth — cloud-sql-python-connector(enable_iam_auth=True) 호출에 필요.
resource "google_project_iam_member" "api_server_cloudsql_client" {
  count   = var.enable_cloud_run ? 1 : 0
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api_server[0].email}"
}

resource "google_project_iam_member" "api_server_cloudsql_instance_user" {
  count   = var.enable_cloud_run ? 1 : 0
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.api_server[0].email}"
}

# Cloud Run default SA는 기본으로 logging.logWriter 보유 — 명시 SA 사용 시 직접 부여 필요.
resource "google_project_iam_member" "api_server_log_writer" {
  count   = var.enable_cloud_run ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.api_server[0].email}"
}

# bucket/AR/secret 접근은 본 SA를 tfvars(`api_server_service_account`)에 채우는
# PR2에서 자동 활성화 — 기존 conditional(var.api_server_service_account != "")이
# SA를 writer/reader/accessor에 자동 포함. 본 PR은 SA 생성만 (Cloud Run 미전환).

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
    # OAuth 콜백(GET /api/v1/auth/callback) 처리 후 브라우저를 돌려보낼 프론트 주소.
    # 2단계 apply — 프론트 배포(module.frontend) 후 var.frontend_url을 채우면 반영된다.
    FRONTEND_URL = var.frontend_url
    # SkillDocumentStore(ADR-0017 이중 저장) — 일반 GCS_BUCKET_NAME과 분리된 전용 버킷.
    # secret 아닌 단순 이름이라 plaintext env (secret_env_vars 아님).
    SKILLS_MARKETPLACE_BUCKET = module.skills_marketplace_bucket.bucket_name
  }

  # PR #80 GCP Secret Manager + 본 PR-C 신규 추가(jwt/encryption/google) — Cloud Run이 직접 주입.
  # api_server는 startup 시 `os.getenv` + Settings(pydantic-settings)로 읽음. plaintext env 회피.
  secret_env_vars = {
    REDIS_URL            = { secret_id = "redis-url", version = "latest" }
    CLOUD_SQL_INSTANCE   = { secret_id = "cloud-sql-instance", version = "latest" }
    DB_IAM_USER          = { secret_id = "db-iam-user", version = "latest" }
    DB_NAME              = { secret_id = "db-name", version = "latest" }
    JWT_SECRET_KEY       = { secret_id = "jwt-secret-key", version = "latest" }
    ENCRYPTION_KEY       = { secret_id = "encryption-key", version = "latest" }
    GOOGLE_CLIENT_ID     = { secret_id = "google-client-id", version = "latest" }
    GOOGLE_CLIENT_SECRET = { secret_id = "google-client-secret", version = "latest" }
    GOOGLE_REDIRECT_URI  = { secret_id = "google-redirect-uri", version = "latest" }
  }

  labels = merge(local.common_labels, { role = "api-server" })

  depends_on = [module.networking, module.redis, module.agent_secrets, module.skills_marketplace_bucket]
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
  }

  # PR #80 GCP Secret Manager에서 직접 주입 — load_secrets_to_env 우회.
  # container.create_container()가 boot 시 KeyError 없이 모든 env를 읽는다.
  # ENCRYPTION_KEY: ADR-0018 Phase 2b — CatalogNodeExecutor가 credential 노드 실행 시
  # AESGCMCipher로 encrypted_data/access_token을 복호화한다. worker SA는
  # effective_secret_accessors에 포함되어 encryption-key accessor를 이미 보유.
  secret_env_vars = {
    REDIS_URL          = { secret_id = "redis-url", version = "latest" }
    CLOUD_SQL_INSTANCE = { secret_id = "cloud-sql-instance", version = "latest" }
    DB_IAM_USER        = { secret_id = "db-iam-user", version = "latest" }
    DB_NAME            = { secret_id = "db-name", version = "latest" }
    LLM_BASE_URL       = { secret_id = "llm-base-url", version = "latest" }
    EMBEDDING_BASE_URL = { secret_id = "embedding-base-url", version = "latest" }
    ENCRYPTION_KEY     = { secret_id = "encryption-key", version = "latest" }
  }

  labels = merge(local.common_labels, { role = "execution-worker" })

  depends_on = [module.networking, module.redis, module.agent_secrets]
}

# ---------------------------------------------------------------------------
# frontend 전용 런타임 SA (PR #140 리뷰 LOW 반영)
# public 진입점 + GCP API(secret/DB) 미사용 → role 부여 0 (AR reader만 reader_members 경유).
# 공용 cloudsql-iam-modal SA 재사용 금지 — 침해 시 blast radius 축소.
# lifecycle precondition — enable_frontend 활성 시 필수 입력 fail-fast (plan 단계).
# ---------------------------------------------------------------------------
resource "google_service_account" "frontend" {
  count        = var.enable_frontend ? 1 : 0
  project      = var.project_id
  account_id   = "workflow-frontend-${var.environment}"
  display_name = "REQ-010 frontend Cloud Run runtime SA (least privilege)"

  lifecycle {
    precondition {
      condition     = var.frontend_image != ""
      error_message = "enable_frontend=true 시 var.frontend_image(AR 이미지 경로:TAG)는 필수입니다."
    }
    precondition {
      condition     = var.enable_cloud_run
      error_message = "enable_frontend=true는 enable_cloud_run=true 전제입니다 — API_PROXY_TARGET이 api_server URL을 참조합니다."
    }
  }
}

# ---------------------------------------------------------------------------
# Cloud Run — REQ-010 frontend (Next.js). 단일 출처 토폴로지(A):
# 프론트가 public 진입점이고, next.config rewrites가 /api/* 를 api_server로
# 프록시한다 (API_PROXY_TARGET env). 브라우저는 프론트 URL 하나만 보므로
# OAuth 쿠키가 same-origin으로 동작한다 (CORS·크로스도메인 쿠키 불필요).
# var.enable_frontend = true + var.frontend_image 지정으로 활성화.
# enable_cloud_run=true 전제 — API_PROXY_TARGET이 api_server URL을 참조한다.
# ---------------------------------------------------------------------------
module "frontend" {
  count  = var.enable_frontend ? 1 : 0
  source = "../../modules/cloud-run"

  project_id            = var.project_id
  region                = var.region
  service_name          = "workflow-frontend-${var.environment}"
  image                 = var.frontend_image
  service_account_email = google_service_account.frontend[0].email
  vpc_connector_id      = module.networking.serverless_connector_id
  vpc_egress            = "PRIVATE_RANGES_ONLY"
  cpu                   = "1"
  memory                = "1Gi"
  min_instances         = 0
  max_instances         = 5
  container_port        = 3000 # Next.js — Dockerfile EXPOSE 3000 + `next start`
  allow_public_access   = true # 단일 출처 진입점이라 public
  ingress               = "INGRESS_TRAFFIC_ALL"
  cpu_idle              = true # 프론트는 request 기반 — idle 시 CPU 미할당

  # API_PROXY_TARGET — next.config rewrites가 /api/* 를 프록시할 대상 (서버사이드 env, NEXT_PUBLIC_ 아님).
  # api_server는 public이라 프론트가 공개 인터넷으로 호출한다 (VPC connector는 모듈 필수라 부착만, 미사용).
  env_vars = {
    ENVIRONMENT      = var.environment
    API_PROXY_TARGET = try(module.api_server[0].service_url, "")
  }

  labels = merge(local.common_labels, { role = "frontend" })

  depends_on = [module.networking]
}
