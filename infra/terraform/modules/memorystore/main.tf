resource "google_redis_instance" "redis" {
  project        = var.project_id
  region         = var.region
  name           = "${var.instance_name}-${var.environment}"
  tier           = var.tier
  memory_size_gb = var.memory_size_gb
  redis_version  = var.redis_version

  authorized_network = var.authorized_network
  connect_mode       = "PRIVATE_SERVICE_ACCESS"

  auth_enabled            = var.auth_enabled
  transit_encryption_mode = var.transit_encryption_mode

  display_name = "Workflow Automation ${var.environment} Redis"
  labels       = var.labels
}
