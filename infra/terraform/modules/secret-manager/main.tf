resource "google_secret_manager_secret" "this" {
  for_each = toset(var.secret_names)

  project   = var.project_id
  secret_id = each.key

  replication {
    auto {}
  }

  lifecycle {
    ignore_changes = [
      labels,
      annotations,
    ]
  }
}

locals {
  accessor_pairs = flatten([
    for secret_name in var.secret_names : [
      for member in var.accessor_members : {
        secret = secret_name
        member = member
      }
    ]
  ])
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each = {
    for pair in local.accessor_pairs :
    "${pair.secret}::${pair.member}" => pair
  }

  project   = var.project_id
  secret_id = google_secret_manager_secret.this[each.value.secret].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}
