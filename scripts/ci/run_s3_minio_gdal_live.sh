#!/usr/bin/env bash
# Detached disposable MinIO, real boto3 + GDAL. Runs in CI (ci.yml, Raster Service
# Tests) and locally; never against a shared or production store.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if ! command -v docker >/dev/null 2>&1; then
  echo 'NOT_RUN_DOCKER_UNAVAILABLE: no Docker binary; this is NOT a passing integration test' >&2
  exit 3
fi
if ! docker compose version >/dev/null 2>&1; then
  echo 'NOT_RUN_DOCKER_COMPOSE_UNAVAILABLE: install Docker Compose plugin' >&2
  exit 3
fi
if ! command -v curl >/dev/null 2>&1; then
  echo 'NOT_RUN_CURL_UNAVAILABLE: curl is required for direct HTTP health probe' >&2
  exit 3
fi
# Any operator override MUST remain digest-pinned; never execute an unpinned image.
: "${S3_TEST_MINIO_IMAGE:=coollabsio/minio:2025-04-22T22-12-26Z@sha256:a4938f37f1be1841b8e7b627ad0207b265345fd0d063e42d7410c78af0e63e68}"
if [[ ! "$S3_TEST_MINIO_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo 'NOT_RUN_UNPINNED_MINIO_IMAGE: specify image@sha256:<64 lowercase hex>' >&2
  exit 3
fi
export S3_TEST_MINIO_IMAGE
: "${S3_TEST_ROOT_USER:=sahool-s3-acceptance}"
: "${S3_TEST_ROOT_PASSWORD:=$(python3 -c 'import secrets; print(secrets.token_urlsafe(28))')}"
: "${S3_TEST_HOST_PORT:=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')}"
: "${S3_TEST_PROJECT:=sahool-s3-acceptance-$(python3 -c 'import secrets; print(secrets.token_hex(4))')}"
export S3_TEST_ROOT_USER S3_TEST_ROOT_PASSWORD S3_TEST_HOST_PORT S3_TEST_PROJECT
COMPOSE="$ROOT/tests/integration/s3_minio_gdal.compose.yml"
cleanup() {
  docker compose -p "$S3_TEST_PROJECT" -f "$COMPOSE" down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
printf 'Starting isolated MinIO on host loopback 127.0.0.1:%s (no production volumes)\n' "$S3_TEST_HOST_PORT"
docker compose -p "$S3_TEST_PROJECT" -f "$COMPOSE" up -d --wait --wait-timeout 90
CONTAINER_ID="$(docker compose -p "$S3_TEST_PROJECT" -f "$COMPOSE" ps -q s3-acceptance-minio)"
if [[ -z "$CONTAINER_ID" ]]; then
  echo 'MINIO_LAB_CONTAINER_MISSING: expected ephemeral service did not start' >&2
  exit 2
fi
S3_TEST_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$CONTAINER_ID")"
export S3_TEST_IMAGE_ID
# No redirects allowed on the health endpoint. Test the API port, not the web console.
STATUS="$(curl -sS --max-time 8 --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:${S3_TEST_HOST_PORT}/minio/health/live")"
if [[ "$STATUS" != "200" ]]; then
  echo "MINIO_HTTP_GATE_FAILED: /minio/health/live returned status=$STATUS; required 200 without redirect" >&2
  exit 2
fi
export SAHOOL_S3_ACCEPTANCE_DISPOSABLE=1
python3 "$ROOT/scripts/ci/s3_minio_gdal_live_acceptance.py" \
  --endpoint "http://127.0.0.1:${S3_TEST_HOST_PORT}" \
  --report "${S3_TEST_REPORT:-${TMPDIR:-/tmp}/sahool-s3-${S3_TEST_PROJECT}.json}"
