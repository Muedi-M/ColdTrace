#!/usr/bin/env bash
# ColdTrace BigQuery Batch Load Commands (Region: africa-south1)

PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
DATASET="coldtrace_warehouse"
LOCATION="africa-south1"

bq --location="${LOCATION}" mk --dataset \
  --description="ColdTrace cold-chain telemetry and validation warehouse" \
  "${PROJECT_ID}:${DATASET}" || true

bq --location="${LOCATION}" load \
  --source_format=CSV \
  --skip_leading_rows=1 \
  --autodetect \
  --replace \
  "${PROJECT_ID}:${DATASET}.sample_14d" \
  ./data/sample_14d.csv

bq --location="${LOCATION}" load \
  --source_format=CSV \
  --skip_leading_rows=1 \
  --autodetect \
  --replace \
  "${PROJECT_ID}:${DATASET}.cold_chain_labeled_2022_2026" \
  ./data/cold_chain_labeled_2022_2026.csv
