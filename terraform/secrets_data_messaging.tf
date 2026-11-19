resource "google_secret_manager_secret" "app_secrets" {
  for_each = toset([
    "NVIDIA_API_KEY",
    "EVIDENCE_HMAC_KEY",
    "API_KEY_HASHES_JSON"
  ])
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "runtime_secret_access" {
  for_each  = google_secret_manager_secret.app_secrets
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime_sa.email}"
}

resource "google_artifact_registry_repository" "coldtrace_repo" {
  location      = var.region
  repository_id = "coldtrace"
  format        = "DOCKER"
  description   = "ColdTrace container repository"

  cleanup_policies {
    id     = "keep-latest-2"
    action = "KEEP"
    most_recent_versions {
      keep_count = 2
    }
  }
  cleanup_policies {
    id     = "expire-old"
    action = "DELETE"
    condition {
      older_than = "86400s"
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_topic" "telemetry_events" {
  name       = "coldtrace-telemetry-events"
  depends_on = [google_project_service.apis]
}

resource "google_firestore_database" "coldtrace_db" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.apis]
}

resource "google_bigquery_dataset" "warehouse" {
  dataset_id = "coldtrace_warehouse"
  location   = "US"
  depends_on = [google_project_service.apis]
}

resource "google_bigquery_table" "telemetry" {
  dataset_id          = google_bigquery_dataset.warehouse.dataset_id
  table_id            = "telemetry_2022_2026"
  deletion_protection = false

  time_partitioning {
    type  = "MONTH"
    field = "Timestamp"
  }

  schema = jsonencode([
    { name = "Storage_Location_ID", type = "STRING", mode = "REQUIRED" },
    { name = "Timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "Warehouse_Temperature_C", type = "FLOAT", mode = "NULLABLE" },
    { name = "Warehouse_Humidity_Percent", type = "FLOAT", mode = "NULLABLE" },
    { name = "Cooling_Load_Percent", type = "FLOAT", mode = "NULLABLE" },
    { name = "Sensor_Connectivity", type = "FLOAT", mode = "NULLABLE" },
    { name = "Exception_Type", type = "STRING", mode = "NULLABLE" }
  ])
}
