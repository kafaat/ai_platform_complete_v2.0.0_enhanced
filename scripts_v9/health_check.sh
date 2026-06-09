#!/usr/bin/env bash
# SAHOOL v9.0 -- Standalone Health Check Script
# Can be run from cron or monitoring systems

set -euo pipefail 2>/dev/null || set -euo pipefail

ENDPOINTS=(
    "http://localhost:8120/healthz|Auth"
    "http://localhost:8091/healthz|Sentinel-MCP"
    "http://localhost:8092/healthz|Weather-MCP"
    "http://localhost:8093/healthz|WOFOST-MCP"
    "http://localhost:8094/healthz|Market-MCP"
    "http://localhost:8096/healthz|Supervisor"
    "http://localhost:8097/healthz|Guardrails"
    "http://localhost:8100/healthz|Edge-AI"
)

FAILED=0
TIMESTAMP=$(date -Iseconds)
REPORT_FILE="/tmp/sahool_health_${TIMESTAMP}.json"

echo "{\"timestamp\": \"$TIMESTAMP\", \"checks\": [" > "$REPORT_FILE"

FIRST=true
for ep in "${ENDPOINTS[@]}"; do
    IFS='|' read -r url name <<< "$ep"
    if curl -sf "$url" >/dev/null 2>&1; then
        status="PASS"
        latency=$(curl -sf -w "%{time_total}" -o /dev/null "$url")
    else
        status="FAIL"
        latency="null"
        FAILED=$((FAILED+1))
    fi

    if [[ "$FIRST" == "true" ]]; then
        FIRST=false
    else
        echo "," >> "$REPORT_FILE"
    fi

    echo "{\"service\": \"$name\", \"status\": \"$status\", \"latency_s\": $latency}" >> "$REPORT_FILE"
done

echo "]}" >> "$REPORT_FILE"

if [[ $FAILED -gt 0 ]]; then
    echo "[CRITICAL] $FAILED services failed health check"
    cat "$REPORT_FILE"
    exit 1
else
    echo "[OK] All services healthy"
    exit 0
fi
