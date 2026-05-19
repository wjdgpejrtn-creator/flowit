variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "instance_name" {
  description = "Cloud SQL instance name"
  type        = string
}

variable "database_version" {
  description = "PostgreSQL version (POSTGRES_15 / POSTGRES_16)"
  type        = string
  default     = "POSTGRES_16"
}

variable "tier" {
  description = "Machine tier (db-f1-micro for staging, db-custom-N-M for production)"
  type        = string
  default     = "db-f1-micro"
}

variable "availability_type" {
  description = "ZONAL (single zone, staging) or REGIONAL (HA, production)"
  type        = string
  default     = "ZONAL"
}

variable "disk_size_gb" {
  description = "Disk size in GB"
  type        = number
  default     = 10
}

variable "disk_autoresize" {
  description = "Auto-resize disk on usage growth"
  type        = bool
  default     = true
}

variable "private_network" {
  description = "VPC self_link for Private IP (from networking module)"
  type        = string
}

variable "service_networking_connection" {
  description = "Service networking connection ID (depends_on)"
  type        = string
}

variable "iam_authentication_enabled" {
  description = "Enable Cloud SQL IAM database authentication"
  type        = bool
  default     = true
}

variable "deletion_protection" {
  description = "Prevent accidental instance deletion"
  type        = bool
  default     = true
}

variable "database_name" {
  description = "Initial database to create"
  type        = string
  default     = "workflow_automation"
}

variable "iam_users" {
  description = "IAM service account emails or user emails to register as IAM DB users"
  type        = list(string)
  default     = []
}

variable "backup_enabled" {
  description = "Enable automated backups"
  type        = bool
  default     = true
}

variable "backup_start_time" {
  description = "Backup window start (HH:MM UTC)"
  type        = string
  default     = "17:00"
}

variable "labels" {
  description = "Resource labels"
  type        = map(string)
  default     = {}
}
