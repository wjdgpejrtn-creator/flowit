resource "google_storage_bucket" "bucket" {
  project                     = var.project_id
  name                        = var.bucket_name
  location                    = var.location
  storage_class               = var.storage_class
  force_destroy               = var.force_destroy
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = var.versioning_enabled
  }

  dynamic "lifecycle_rule" {
    for_each = var.lifecycle_age_days > 0 ? [1] : []
    content {
      action {
        type = "Delete"
      }
      condition {
        age = var.lifecycle_age_days
      }
    }
  }

  labels = var.labels
}

resource "google_storage_bucket_iam_member" "writers" {
  for_each = toset(var.writer_members)

  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.objectAdmin"
  member = each.value
}

resource "google_storage_bucket_iam_member" "readers" {
  for_each = toset(var.reader_members)

  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.objectViewer"
  member = each.value
}
