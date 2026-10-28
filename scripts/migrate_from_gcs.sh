#!/usr/bin/env bash
# One-time copy of the existing data from the GCS bucket into the new S3 bucket.
# Needs gcloud (logged in to the GCP project) and aws (credentials for the target account).
# Usage: scripts/migrate_from_gcs.sh <gcs-bucket> <s3-bucket> [prefix]
#   e.g. scripts/migrate_from_gcs.sh shrey-snowviz-platform snowviz-platform-tiles data
set -euo pipefail

GCS_BUCKET="$1"
S3_BUCKET="$2"
PREFIX="${3:-data}"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

echo "Downloading gs://$GCS_BUCKET/$PREFIX to $STAGING (GCS egress charges apply)"
gcloud storage rsync --recursive "gs://$GCS_BUCKET/$PREFIX" "$STAGING/$PREFIX"

echo "Uploading to s3://$S3_BUCKET/$PREFIX"
aws s3 sync "$STAGING/$PREFIX" "s3://$S3_BUCKET/$PREFIX" --cache-control "public, max-age=604800"
