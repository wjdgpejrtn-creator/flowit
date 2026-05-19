variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
}

variable "image" {
  description = "Container image (e.g. gcr.io/PROJECT/api-server:latest)"
  type        = string
}

variable "service_account_email" {
  description = "Runtime service account email"
  type        = string
}

variable "vpc_connector_id" {
  description = "Serverless VPC Access connector ID (from networking module)"
  type        = string
}

variable "vpc_egress" {
  description = "VPC egress mode: ALL_TRAFFIC or PRIVATE_RANGES_ONLY"
  type        = string
  default     = "PRIVATE_RANGES_ONLY"
}

variable "cpu" {
  description = "CPU limit (e.g. 1, 2, 4)"
  type        = string
  default     = "1"
}

variable "memory" {
  description = "Memory limit (e.g. 512Mi, 1Gi, 2Gi)"
  type        = string
  default     = "512Mi"
}

variable "min_instances" {
  description = "Minimum container instances (0 = scale to zero)"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum container instances"
  type        = number
  default     = 10
}

variable "container_port" {
  description = "Container listen port"
  type        = number
  default     = 8080
}

variable "env_vars" {
  description = "Plain environment variables (name -> value)"
  type        = map(string)
  default     = {}
}

variable "secret_env_vars" {
  description = "Secret Manager env vars (env_name -> {secret_id, version})"
  type = map(object({
    secret_id = string
    version   = string
  }))
  default = {}
}

variable "allow_public_access" {
  description = "Allow allUsers to invoke the service (public HTTP)"
  type        = bool
  default     = false
}

variable "ingress" {
  description = "Cloud Run v2 ingress mode: INGRESS_TRAFFIC_ALL | INGRESS_TRAFFIC_INTERNAL_ONLY | INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER. worker는 internal-only 권장."
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"
}

variable "cpu_idle" {
  description = "Cloud Run v2 CPU 할당 모드. false = always-on CPU (long-running celery worker용, instance billable always). true(default) = request 처리 중에만 CPU 할당."
  type        = bool
  default     = true
}

variable "labels" {
  description = "Resource labels"
  type        = map(string)
  default     = {}
}
