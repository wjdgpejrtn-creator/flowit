terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "workflow-auto-tfstate"
    prefix = "staging"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "agent_secrets" {
  source = "../../modules/secret-manager"

  project_id       = var.project_id
  secret_names     = var.agent_secret_names
  accessor_members = var.agent_secret_accessors
}
