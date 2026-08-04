#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${NATS_URL:=nats://localhost:4222}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

command -v psql >/dev/null || { echo 'psql is required' >&2; exit 127; }
python - <<'PY'
import importlib.util
missing=[m for m in ('asyncpg','nats') if importlib.util.find_spec(m) is None]
if missing:
    raise SystemExit('missing Python dependencies: '+', '.join(missing))
PY

psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f scripts/e2e/command_event_causality_live_gate.sql
psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f scripts/e2e/canonical_execution_learning_rls_live_gate.sql
DATABASE_URL="$DATABASE_URL" NATS_URL="$NATS_URL" \
  python scripts/workers/canonical_execution_learning_worker.py --preflight

echo 'PASS canonical_execution_learning_live_gate'
