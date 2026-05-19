variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "location" {
  description = "Bucket location (region or multi-region)"
  type        = string
}

variable "bucket_name" {
  description = "Globally unique bucket name"
  type        = string
}

variable "storage_class" {
  description = "Storage class"
  type        = string
  default     = "STANDARD"
}

variable "versioning_enabled" {
  description = "Enable object versioning (production recommended)"
  type        = bool
  default     = false
}

variable "force_destroy" {
  description = "Allow non-empty bucket deletion (staging only)"
  type        = bool
  default     = false
}

variable "lifecycle_age_days" {
  description = "Auto-delete objects older than N days (0 = disabled)"
  type        = number
  default     = 0
}

variable "writer_members" {
  description = "IAM principals with object create/update permission (e.g. Modal SA)"
  type        = list(string)
  default     = []
}

variable "reader_members" {
  description = "IAM principals with read-only permission (e.g. team members for debugging)"
  type        = list(string)
  default     = []
}

variable "labels" {
  description = "Resource labels"
  type        = map(string)
  default     = {}
}
