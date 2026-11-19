variable "project_id" {
  type        = string
  description = "Target GCP Project ID"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "github_owner" {
  type    = string
  default = "MOORTHYrm"
}

variable "github_repo" {
  type    = string
  default = "MOORTHYrm/coldtrace"
}

variable "alert_email" {
  type        = string
  description = "Recipient email for Cloud Monitoring alerts"
}

variable "image_tag" {
  type    = string
  default = "latest"
}
