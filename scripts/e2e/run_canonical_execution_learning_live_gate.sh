#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${NATS_URL:=nats://localhost:4222}"
: "${LIVE_EVIDENCE_OUTPUT:=artifacts/runtime/canonical_execution_learning_live_evidence.json}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

command -v psql >/dev/null || { echo 'psql is required' >&2; exit 127; }
python - <<'PY'
import importlib.util
missing=[m for m in ('asyncpg','nats') if importlib.util.find_spec(m) is None]
if missing:
    raise SystemExit('missing Python dependencies: '+', '.join(missing))
PY

if [[ -n "${EXPECTED_SHA:-}" ]]; then
  [[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'EXPECTED_SHA must be a full lowercase SHA-1' >&2; exit 2; }
  checkout_sha="$(git rev-parse HEAD)"
  [[ "$checkout_sha" == "$EXPECTED_SHA" ]] || {
    echo "checkout SHA mismatch: expected=$EXPECTED_SHA checkout=$checkout_sha" >&2
    exit 2
  }
else
  EXPECTED_SHA="$(git rev-parse HEAD 2>/dev/null || true)"
  [[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || {
    echo 'EXPECTED_SHA is required outside a git checkout' >&2
    exit 2
  }
fi

# A SHA identifies a tree; uncommitted changes mean the tree that ran is NOT the tree the
# evidence names. Measured: this gate first passed with three production fixes still
# unstaged, and stamped a SHA whose checkout could not have passed it — a green result
# attributed to the wrong commit is worse than a red one. Checked after the SHA is
# resolved so an explicit EXPECTED_SHA cannot smuggle a dirty tree past it either.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  dirty="$(git status --porcelain)"
  if [[ -n "$dirty" ]]; then
    echo 'working tree is dirty — evidence would name a SHA that was not what ran:' >&2
    echo "$dirty" >&2
    exit 2
  fi
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" \
  -f scripts/e2e/command_event_causality_live_gate.sql \
  >"$workdir/causality.log" 2>&1
psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" \
  -f scripts/e2e/canonical_execution_learning_rls_live_gate.sql \
  >"$workdir/rls.log" 2>&1
DATABASE_URL="$DATABASE_URL" NATS_URL="$NATS_URL" \
  python services/sahool-platform/workers/canonical_execution_learning_worker.py --preflight-json \
  >"$workdir/preflight.json"
DATABASE_URL="$DATABASE_URL" NATS_URL="$NATS_URL" \
  python scripts/e2e/canonical_projection_jetstream_roundtrip.py \
  >"$workdir/jetstream_roundtrip.json"

mkdir -p "$(dirname "$LIVE_EVIDENCE_OUTPUT")"
EXPECTED_SHA="$EXPECTED_SHA" LIVE_EVIDENCE_OUTPUT="$LIVE_EVIDENCE_OUTPUT" WORKDIR="$workdir" python - <<'PY'
from __future__ import annotations
import hashlib, json, os
from datetime import UTC, datetime
from pathlib import Path

wd=Path(os.environ['WORKDIR'])
def digest(name: str) -> str:
    return hashlib.sha256((wd/name).read_bytes()).hexdigest()
preflight=json.loads((wd/'preflight.json').read_text(encoding='utf-8'))
payload={
  'schema_version': 1,
  'generated_at_utc': datetime.now(UTC).isoformat(),
  'tested_sha': os.environ['EXPECTED_SHA'],
  'verdict': 'runtime_qualification_candidate',
  'production_certified': False,
  'checks': {
    'command_event_causality': {'status':'passed','output_sha256':digest('causality.log')},
    'tenant_rls': {'status':'passed','output_sha256':digest('rls.log')},
    'worker_preflight': {'status':'passed','facts':preflight,'output_sha256':digest('preflight.json')},
    'jetstream_projection_roundtrip': {'status':'passed','facts':json.loads((wd/'jetstream_roundtrip.json').read_text(encoding='utf-8')),'output_sha256':digest('jetstream_roundtrip.json')},
  },
  'truth_boundary': 'This evidence proves live PostgreSQL causality/RLS, JetStream subject coverage, and one publish-consume-persist-ack round trip with replay idempotency. It does not prove soak, disaster recovery, or production certification.',
}
out=Path(os.environ['LIVE_EVIDENCE_OUTPUT'])
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(f'PASS canonical_execution_learning_live_gate evidence={out}')
PY
