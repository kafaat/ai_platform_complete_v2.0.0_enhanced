#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost}"
JWT="${SAHOOL_JWT:-}"
if [[ -n "$JWT" ]]; then
  curl -skf -H "Authorization: Bearer $JWT" "${BASE_URL%/}/api/v1/admin/outbox/dead-letter" >/tmp/sahool_outbox_dlq.json \
    && echo "OK: admin DLQ endpoint reachable" \
    || echo "WARN: admin DLQ endpoint unavailable or unauthorized"
else
  echo "SKIP: SAHOOL_JWT not set; admin DLQ HTTP check skipped"
fi
if [[ -n "${DATABASE_URL:-}" ]] && command -v psql >/dev/null 2>&1; then
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT status, count(*) FROM event_outbox GROUP BY status ORDER BY status;"
else
  echo "SKIP: DATABASE_URL/psql unavailable; DB outbox query skipped"
fi
