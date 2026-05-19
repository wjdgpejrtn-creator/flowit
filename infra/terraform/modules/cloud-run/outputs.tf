output "service_name" {
  description = "Cloud Run service name"
  value       = google_cloud_run_v2_service.service.name
}

output "service_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.service.uri
}

output "latest_revision" {
  description = "Latest ready revision"
  value       = google_cloud_run_v2_service.service.latest_ready_revision
}
