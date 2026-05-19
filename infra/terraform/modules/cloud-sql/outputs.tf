output "instance_name" {
  description = "Cloud SQL instance name"
  value       = google_sql_database_instance.instance.name
}

output "connection_name" {
  description = "Cloud SQL Connector connection name (project:region:instance)"
  value       = google_sql_database_instance.instance.connection_name
}

output "private_ip_address" {
  description = "Cloud SQL Private IP"
  value       = google_sql_database_instance.instance.private_ip_address
}

output "self_link" {
  description = "Instance self link"
  value       = google_sql_database_instance.instance.self_link
}

output "database_name" {
  description = "Initial database name"
  value       = google_sql_database.database.name
}
