resource "google_sql_database_instance" "instance" {
  project             = var.project_id
  name                = var.instance_name
  region              = var.region
  database_version    = var.database_version
  deletion_protection = var.deletion_protection

  depends_on = [var.service_networking_connection]

  settings {
    tier              = var.tier
    availability_type = var.availability_type
    disk_size         = var.disk_size_gb
    disk_autoresize   = var.disk_autoresize
    disk_type         = "PD_SSD"

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = var.private_network
      enable_private_path_for_google_cloud_services = true
    }

    backup_configuration {
      enabled                        = var.backup_enabled
      start_time                     = var.backup_start_time
      point_in_time_recovery_enabled = var.backup_enabled
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = var.iam_authentication_enabled ? "on" : "off"
    }

    user_labels = var.labels
  }
}

resource "google_sql_database" "database" {
  project  = var.project_id
  instance = google_sql_database_instance.instance.name
  name     = var.database_name
}

# IAM database users (SA emails or user emails — type auto-detected by Google)
resource "google_sql_user" "iam_users" {
  for_each = toset(var.iam_users)

  project  = var.project_id
  instance = google_sql_database_instance.instance.name
  name     = each.value
  type     = endswith(each.value, ".gserviceaccount.com") ? "CLOUD_IAM_SERVICE_ACCOUNT" : "CLOUD_IAM_USER"
}
