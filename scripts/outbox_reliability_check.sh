#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost}"
JWT="${SAHOOL_JWT:-}"
if [[ -n "$JWT" ]]; then
  if ! code=$(curl -sS -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $JWT" \
    "${BASE_URL%/}/api/v1/admin/outbox/dead-letter"); then
    echo "FAIL: admin DLQ transport error" >&2
    exit 1
  fi
  if [[ ! "$code" =~ ^2[0-9][0-9]$ ]]; then
    echo "FAIL: admin DLQ endpoint unavailable or unauthorized ($code)" >&2
    exit 1
  fi
  echo "OK: admin DLQ endpoint reachable"
else
  echo "SKIP: SAHOOL_JWT not set; admin DLQ HTTP check skipped"
fi
if [[ -n "${DATABASE_URL:-}" ]] && command -v psql >/dev/null 2>&1; then
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT status, count(*) FROM event_outbox GROUP BY status ORDER BY status;"
else
  echo "SKIP: DATABASE_URL/psql unavailable; DB outbox query skipped"
fi
