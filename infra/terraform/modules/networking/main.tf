resource "google_compute_network" "vpc" {
  project                 = var.project_id
  name                    = "${var.vpc_name}-${var.environment}"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "subnet" {
  project                  = var.project_id
  name                     = "${var.vpc_name}-${var.environment}-subnet"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
}

# Serverless VPC Access connector (Cloud Run / Cloud Functions → VPC private resources)
resource "google_vpc_access_connector" "serverless_connector" {
  project       = var.project_id
  name          = "${var.vpc_name}-${var.environment}-conn"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = var.connector_cidr
  machine_type  = "e2-micro"
  min_instances = 2
  max_instances = 3
}

# Cloud SQL / Memorystore Private IP peering (service networking)
resource "google_compute_global_address" "private_ip_alloc" {
  project       = var.project_id
  name          = "${var.private_ip_range_name}-${var.environment}"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = var.private_ip_prefix_length
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloc.name]
}
