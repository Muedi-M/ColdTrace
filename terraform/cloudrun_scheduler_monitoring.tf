resource "google_cloud_run_v2_service" "coldtrace_app" {
  name     = "coldtrace-app"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.coldtrace_repo.repository_id}/coldtrace-app:${var.image_tag}"

      resources {
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
        cpu_idle = true
      }

      env {
        name  = "ENV"
        value = "production"
      }
      env {
        name  = "USE_FIRESTORE"
        value = "true"
      }
      env {
        name  = "USE_BIGQUERY"
        value = "true"
      }
      env {
        name  = "PUBSUB_TOPIC"
        value = google_pubsub_topic.telemetry_events.name
      }

      dynamic "env" {
        for_each = google_secret_manager_secret.app_secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.runtime_secret_access]
}

resource "google_cloud_scheduler_job" "simulated_ingest" {
  name             = "coldtrace-simulated-sensor-ingest"
  description      = "Triggers simulated cold-chain telemetry for JHB-DC01, DBN-DC02, and CPT-DC03"
  schedule         = "*/15 * * * *"
  time_zone        = "UTC"
  attempt_deadline = "60s"
  region           = var.region

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.coldtrace_app.uri}/ingest"
    headers = {
      "Content-Type" = "application/json"
    }
    body = base64encode(jsonencode({
      location_id                  = "JHB-DC01"
      warehouse_temperature_c      = 4.2
      warehouse_humidity_percent   = 62.0
      cooling_load_percent         = 54.0
      sensor_connectivity          = 99.2
    }))
  }

  depends_on = [google_cloud_run_v2_service.coldtrace_app]
}

resource "google_monitoring_notification_channel" "ops_email" {
  display_name = "ColdTrace Security & Ops Email Alert"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
  depends_on = [google_project_service.apis]
}

resource "google_logging_metric" "security_rejections" {
  name        = "coldtrace_security_rejections"
  description = "Counts 401, 403, 409, and 429 HTTP responses from ColdTrace"
  filter      = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"coldtrace-app\" AND (httpRequest.status=401 OR httpRequest.status=403 OR httpRequest.status=409 OR httpRequest.status=429)"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "auth_spike" {
  display_name = "ColdTrace - Auth or Security Rejection Spike"
  combiner     = "OR"

  conditions {
    display_name = "More than 15 security rejections in 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.security_rejections.name}\" AND resource.type=\"cloud_run_revision\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 15
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.ops_email.id]
}

resource "google_monitoring_alert_policy" "run_5xx_errors" {
  display_name = "ColdTrace - Cloud Run 5xx Error Spike"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run 5xx error count > 5 in 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"coldtrace-app\" AND metric.labels.response_code_class=\"5xx\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.ops_email.id]
}

output "cloud_run_url" {
  value = google_cloud_run_v2_service.coldtrace_app.uri
}

output "wif_provider" {
  value = google_iam_workload_identity_pool_provider.github_provider.name
}

output "cicd_sa_email" {
  value = google_service_account.cicd_sa.email
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = google_cloud_run_v2_service.coldtrace_app.project
  location = google_cloud_run_v2_service.coldtrace_app.location
  name     = google_cloud_run_v2_service.coldtrace_app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

