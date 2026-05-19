output "vpc_id" {
  description = "VPC network full resource ID"
  value       = google_compute_network.vpc.id
}

output "vpc_name" {
  description = "VPC network name (used by other modules)"
  value       = google_compute_network.vpc.name
}

output "vpc_self_link" {
  description = "VPC self link (used by Cloud SQL / Memorystore)"
  value       = google_compute_network.vpc.self_link
}

output "subnet_id" {
  description = "Primary subnet resource ID"
  value       = google_compute_subnetwork.subnet.id
}

output "serverless_connector_id" {
  description = "Serverless VPC connector ID (Cloud Run egress)"
  value       = google_vpc_access_connector.serverless_connector.id
}

output "private_ip_alloc_name" {
  description = "Reserved range name for service networking peering"
  value       = google_compute_global_address.private_ip_alloc.name
}

output "private_vpc_connection" {
  description = "Service networking connection (Cloud SQL / Memorystore depends_on)"
  value       = google_service_networking_connection.private_vpc_connection.id
}
