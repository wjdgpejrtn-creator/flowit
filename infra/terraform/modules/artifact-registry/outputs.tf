output "repository_id" {
  description = "Created repository ID"
  value       = google_artifact_registry_repository.repo.repository_id
}

output "repository_name" {
  description = "Fully-qualified repository name (projects/.../locations/.../repositories/...)"
  value       = google_artifact_registry_repository.repo.name
}

output "docker_path_prefix" {
  description = "Docker image path prefix (LOCATION-docker.pkg.dev/PROJECT/REPO)"
  value       = "${google_artifact_registry_repository.repo.location}-docker.pkg.dev/${google_artifact_registry_repository.repo.project}/${google_artifact_registry_repository.repo.repository_id}"
}
