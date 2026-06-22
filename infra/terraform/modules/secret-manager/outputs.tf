output "secret_ids" {
  description = "Map of secret_name → fully-qualified secret resource ID (projects/.../secrets/...)"
  value       = { for k, v in google_secret_manager_secret.this : k => v.id }
}

output "secret_names" {
  description = "List of secret IDs that were created (matches var.secret_names)"
  value       = [for v in google_secret_manager_secret.this : v.secret_id]
}
