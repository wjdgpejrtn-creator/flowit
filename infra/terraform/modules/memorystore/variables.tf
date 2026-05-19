variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "environment" {
  description = "Environment name (staging/production)"
  type        = string
}

variable "instance_name" {
  description = "Redis instance name suffix (full name = workflow-redis-{env})"
  type        = string
  default     = "workflow-redis"
}

variable "tier" {
  description = "Redis tier: BASIC (no HA, cheaper) or STANDARD_HA"
  type        = string
  default     = "BASIC"
}

variable "memory_size_gb" {
  description = "Redis memory size in GB"
  type        = number
  default     = 1
}

variable "redis_version" {
  description = "Redis version (REDIS_6_X / REDIS_7_0 / REDIS_7_2)"
  type        = string
  default     = "REDIS_7_2"
}

variable "authorized_network" {
  description = "VPC network self_link or ID (from networking module)"
  type        = string
}

variable "auth_enabled" {
  description = "Enable Redis AUTH (password)"
  type        = bool
  default     = true
}

variable "transit_encryption_mode" {
  description = "Transit encryption: DISABLED or SERVER_AUTHENTICATION"
  type        = string
  default     = "SERVER_AUTHENTICATION"
}

variable "labels" {
  description = "Resource labels"
  type        = map(string)
  default     = {}
}
