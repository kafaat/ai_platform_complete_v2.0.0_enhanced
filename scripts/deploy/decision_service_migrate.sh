#!/usr/bin/env bash
# Decision-service SoR schema migration — explicit, observable, out-of-band pre-deploy step.
#
# Schema promotion is a deliberate RELEASE action, never a startup side effect. This wrapper is
# the single supported way to apply decision-service migrations (001 + 002, including the WX-10.7
# review layer) during DEPLOYED-DECISION-SOR-PROMOTION. It:
#   1. requires DATABASE_URL (the restricted decision-service role — NOT a superuser/BYPASSRLS role);
#   2. requires DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true (fail-closed: refuses to mutate otherwise);
#   3. prints the pre-apply --check state, applies, then prints the post-apply --check state;
#   4. runs the WX-10.7 review parity/quarantine verifier (backfill.py --verify-review) so ambiguous
#      candidates are surfaced BEFORE the ownership flip (never guessed).
#
# It does NOT set DECISION_SERVICE_SOR_ENABLED and does NOT flip ownership — that stays an explicit
# operator action after every gate is green (see the production promotion runbook).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNNER="$REPO_ROOT/services/decision-service/migration_runner.py"
BACKFILL="$REPO_ROOT/services/decision-service/backfill.py"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "::error:: DATABASE_URL is required (restricted decision-service role, not superuser/BYPASSRLS)" >&2
  exit 2
fi
if [[ "${DECISION_SERVICE_ALLOW_SCHEMA_CHANGE:-}" != "true" ]]; then
  echo "::error:: refusing to apply schema: set DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true to proceed" >&2
  exit 2
fi

echo "== decision-service migrate: pre-apply --check =="
python "$RUNNER" --check || echo "(pending migrations present — expected before first apply)"

echo "== decision-service migrate: --apply =="
python "$RUNNER" --apply

echo "== decision-service migrate: post-apply --check (must be clean) =="
python "$RUNNER" --check

echo "== WX-10.7 review parity / quarantine (read-only; resolve any quarantined rows before cutover) =="
python "$BACKFILL" --verify-review

echo "decision_service_migrate_ok"
