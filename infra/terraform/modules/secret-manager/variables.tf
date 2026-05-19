variable "project_id" {
  description = "GCP project ID hosting the secrets"
  type        = string
}

variable "secret_names" {
  description = "Flat list of secret IDs to create"
  type        = list(string)
}

variable "accessor_members" {
  description = "IAM members granted roles/secretmanager.secretAccessor on every secret. Format: user:foo@bar.com, serviceAccount:sa@proj.iam.gserviceaccount.com, etc."
  type        = list(string)
}
