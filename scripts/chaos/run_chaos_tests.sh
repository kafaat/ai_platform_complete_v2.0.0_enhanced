#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.v9.yml}"
BASE_URL="${BASE_URL:-http://localhost}"
FIELD_ID="${FIELD_ID:-}"
TENANT_ID="${TENANT_ID:-}"
SAHOOL_JWT="${SAHOOL_JWT:-}"
CHAOS_WAIT_SECONDS="${CHAOS_WAIT_SECONDS:-15}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for chaos tests." >&2
  exit 127
fi

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }
smoke() {
  BASE_URL="$BASE_URL" bash scripts/runtime_smoke.sh || return 1
}
restore_service() {
  local svc="$1"
  echo "[restore] starting $svc"
  compose up -d "$svc"
  sleep "$CHAOS_WAIT_SECONDS"
}
chaos_stop_start() {
  local svc="$1"
  echo "[chaos] stopping $svc"
  compose stop "$svc" || true
  sleep "$CHAOS_WAIT_SECONDS"
  echo "[chaos] checking degraded behavior after $svc stop"
  curl -fsS "$BASE_URL/api/ai-agronomist/healthz" >/dev/null || true
  curl -fsS "$BASE_URL/api/raster/healthz" >/dev/null || true
  restore_service "$svc"
  echo "[chaos] checking recovery after $svc restart"
  smoke
}

compose config >/dev/null
compose ps
smoke

# Core dependency failures. These should degrade clearly and recover without cache/event corruption.
for svc in sahool-redis sahool-nats sahool-raster-service sahool-rag-retrieval sahool-knowledge-graph sahool-ai-agronomist; do
  if compose ps --services | grep -qx "$svc"; then
    chaos_stop_start "$svc"
  else
    echo "[skip] $svc not present in $COMPOSE_FILE"
  fi
done

# After failures, verify outbox/recovery if credentials are supplied.
if [[ -n "$SAHOOL_JWT" ]]; then
  BASE_URL="$BASE_URL" SAHOOL_JWT="$SAHOOL_JWT" bash scripts/outbox_reliability_check.sh
fi

if [[ -n "$FIELD_ID" && -n "$TENANT_ID" && -n "$SAHOOL_JWT" ]]; then
  BASE_URL="$BASE_URL" FIELD_ID="$FIELD_ID" TENANT_ID="$TENANT_ID" SAHOOL_JWT="$SAHOOL_JWT" bash scripts/e2e/e2e_field_imagery_ai.sh
fi


BASE_URL="$BASE_URL" bash scripts/recovery/recovery_smoke.sh

echo "Chaos/recovery harness completed with blocking recovery checks. Review service logs for restart loops, 5xx spikes, and DLQ growth."
