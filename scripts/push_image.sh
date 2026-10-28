#!/usr/bin/env bash
# Build the pipeline image and push it to the ECR repository created by infra/.
# Usage: scripts/push_image.sh [tag]   (default tag: latest)
set -euo pipefail

cd "$(dirname "$0")/.."
TAG="${1:-latest}"
REPO_URL="$(terraform -chdir=infra output -raw ecr_repository_url)"
REGISTRY="${REPO_URL%%/*}"
REGION="$(echo "$REGISTRY" | cut -d. -f4)"

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/amd64 -t "$REPO_URL:$TAG" .
docker push "$REPO_URL:$TAG"
echo "Pushed $REPO_URL:$TAG"
