variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "environment" {
  description = "Environment name (staging/production)"
  type        = string
}

variable "vpc_name" {
  description = "VPC network name"
  type        = string
  default     = "workflow-vpc"
}

variable "subnet_cidr" {
  description = "Subnet primary CIDR range"
  type        = string
  default     = "10.10.0.0/24"
}

variable "connector_cidr" {
  description = "Serverless VPC Access connector CIDR (/28)"
  type        = string
  default     = "10.10.1.0/28"
}

variable "private_ip_range_name" {
  description = "Reserved range name for Cloud SQL Private IP peering"
  type        = string
  default     = "workflow-private-ip"
}

variable "private_ip_prefix_length" {
  description = "Reserved range prefix length for service networking"
  type        = number
  default     = 16
}
