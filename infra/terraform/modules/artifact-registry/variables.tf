variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "location" {
  description = "Artifact Registry location (regional, e.g. asia-northeast3)"
  type        = string
}

variable "repository_id" {
  description = "Repository name (alphanumeric + hyphen)"
  type        = string
}

variable "format" {
  description = "Repository format: DOCKER | MAVEN | NPM | PYTHON | APT | YUM | GENERIC"
  type        = string
  default     = "DOCKER"
}

variable "description" {
  description = "Human-readable description"
  type        = string
  default     = ""
}

variable "reader_members" {
  description = "IAM principals with artifactregistry.reader (Cloud Run runtime SA가 image pull 시 필요)"
  type        = list(string)
  default     = []
}

variable "writer_members" {
  description = "IAM principals with artifactregistry.writer (Cloud Build / CI가 image push 시 필요)"
  type        = list(string)
  default     = []
}

variable "labels" {
  description = "Resource labels"
  type        = map(string)
  default     = {}
}
