locals {
  data_analyst_email  = "ntokozochantell396@gmail.com"
  ai_foundation_email = "mbambalat@gmail.com"
  cybersecurity_email = "drpeteropiyo@gmail.com"

  ai_foundation_project_roles = toset([
    "roles/run.developer",
    "roles/artifactregistry.writer",
    "roles/pubsub.editor",
    "roles/cloudscheduler.admin",
    "roles/datastore.user",
    "roles/bigquery.jobUser",
    "roles/bigquery.dataViewer",
    "roles/secretmanager.viewer",
    "roles/iam.serviceAccountUser"
  ])

  cybersecurity_project_roles = toset([
    "roles/iam.securityReviewer",
    "roles/logging.viewer",
    "roles/logging.privateLogViewer",
    "roles/monitoring.viewer",
    "roles/secretmanager.viewer",
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser"
  ])
}

# 1. Data Analyst (ntokozochantell396@gmail.com) — Project job runner + Dataset editor
resource "google_project_iam_member" "analyst_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "user:${local.data_analyst_email}"
}

resource "google_bigquery_dataset_iam_member" "analyst_warehouse_editor" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.warehouse.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "user:${local.data_analyst_email}"
}

# 2. AI & Cloud Foundation (mbambalat@gmail.com) — Runtime & Platform Developer
resource "google_project_iam_member" "ai_foundation_roles" {
  for_each = local.ai_foundation_project_roles
  project  = var.project_id
  role     = each.value
  member   = "user:${local.ai_foundation_email}"
}

# 3. Cyber Security (drpeteropiyo@gmail.com) — Security & Audit Reviewer
resource "google_project_iam_member" "cybersecurity_roles" {
  for_each = local.cybersecurity_project_roles
  project  = var.project_id
  role     = each.value
  member   = "user:${local.cybersecurity_email}"
}
