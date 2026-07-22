#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
NGINX="$ROOT/nginx/nginx.v9.conf"
COMPOSE="$ROOT/docker-compose.v9.yml"
required_routes=(
  "/api/raster/"
  "/api/v1/"
  "/api/rag/"
  "/api/knowledge-graph/"
  "/api/ai-agronomist/"
  "/api/guardrails/"
  "/api/soil/"
)
required_services=(
  "sahool-platform"
  "sahool-raster-service"
  "sahool-rag-retrieval"
  "sahool-knowledge-graph"
  "sahool-ai-agronomist"
  "sahool-guardrails-engine"
)
missing=0
for route in "${required_routes[@]}"; do
  if ! grep -q "location .*${route}" "$NGINX"; then
    echo "MISSING_ROUTE $route" >&2
    missing=1
  else
    echo "OK_ROUTE $route"
  fi
done
for svc in "${required_services[@]}"; do
  if ! grep -q "^[[:space:]]*${svc}:" "$COMPOSE"; then
    echo "MISSING_SERVICE $svc" >&2
    missing=1
  else
    echo "OK_SERVICE $svc"
  fi
done
exit "$missing"
