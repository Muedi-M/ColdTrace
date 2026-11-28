#!/usr/bin/env bash
# ColdTrace BigQuery Batch Load Commands
# Run from the repo root. The dataset location must match Terraform (google_bigquery_dataset.warehouse: "US").

PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
DATASET="coldtrace_warehouse"
LOCATION="${BQ_LOCATION:-US}"

bq --location="${LOCATION}" mk --dataset \
  --description="ColdTrace cold-chain telemetry and validation warehouse" \
  "${PROJECT_ID}:${DATASET}" || true

bq --location="${LOCATION}" load \
  --source_format=CSV \
  --skip_leading_rows=1 \
  --autodetect \
  --replace \
  "${PROJECT_ID}:${DATASET}.cold_chain_labeled_2022_2026" \
  ./Backend/data/cold_chain_labeled_2022_2026.csv
