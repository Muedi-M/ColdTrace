# Alerts and case status changes published by the app (coldtrace/pubsub.py) land in BigQuery
# through a BigQuery subscription: no streaming inserts from the app, no extra service to run.
# Insights MVP queries (cycle time, detection-to-review, throughput) can run on this table.

data "google_project" "this" {
  project_id = var.project_id
}

resource "google_bigquery_table" "case_events" {
  dataset_id          = google_bigquery_dataset.warehouse.dataset_id
  table_id            = "case_events"
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "publish_time"
  }

  # Columns required by a BigQuery subscription with write_metadata = true
  schema = jsonencode([
    { name = "subscription_name", type = "STRING", mode = "NULLABLE" },
    { name = "message_id", type = "STRING", mode = "NULLABLE" },
    { name = "publish_time", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "data", type = "STRING", mode = "NULLABLE" },
    { name = "attributes", type = "STRING", mode = "NULLABLE" }
  ])
}

# The Pub/Sub service agent writes to the dataset on the subscription's behalf.
resource "google_bigquery_dataset_iam_member" "pubsub_writer" {
  dataset_id = google_bigquery_dataset.warehouse.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription" "case_events_to_bigquery" {
  name  = "coldtrace-case-events-bq"
  topic = google_pubsub_topic.telemetry_events.id

  # only the app's own alert / case messages; raw readings stay out of this table
  filter = "attributes.type = \"alert\" OR attributes.type = \"case_event\""

  bigquery_config {
    table          = "${var.project_id}.${google_bigquery_dataset.warehouse.dataset_id}.${google_bigquery_table.case_events.table_id}"
    write_metadata = true
  }

  message_retention_duration = "604800s"
  depends_on                 = [google_bigquery_dataset_iam_member.pubsub_writer]
}
