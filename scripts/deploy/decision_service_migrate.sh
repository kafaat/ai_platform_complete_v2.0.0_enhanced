#!/usr/bin/env bash
# Decision-service SoR schema migration — explicit, observable, out-of-band pre-deploy step.
#
# Schema promotion is a deliberate RELEASE action, never a startup side effect. This wrapper is
# the single supported way to apply decision-service migrations (every file under
# services/decision-service/migrations/, including the WX-10.7 review layer) during
# DEPLOYED-DECISION-SOR-PROMOTION. It:
#   1. requires DATABASE_URL = the decision SCHEMA-OWNER (migrator) role: NOSUPERUSER and
#      NOBYPASSRLS, and NOT one of the two application roles. The DML-only decision-service app
#      role cannot apply DDL ("permission denied for schema public"), and an app role that owns
#      the SoR tables fails the pre-cutover role certification. In the same-DB topology the
#      migrator must own the five platform-created SoR tables and the two shared functions
#      sahool_chain_correlation_root / sahool_chain_correlation_immutable (migration 036
#      replaces them) — measured on PG16, see
#      docs/runbooks/DECISION_SERVICE_SOR_STAGING_CUTOVER_RUNBOOK.md;
#   2. requires DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true (fail-closed: refuses to mutate otherwise);
#   3. prints the pre-apply --check state, applies, then prints the post-apply --check state; a
#      pre-check that fails for any reason other than "migrations pending" (exit 2) stops here;
#   4. runs the WX-10.7 review parity/quarantine verifier (backfill.py --verify-review) so ambiguous
#      candidates are surfaced BEFORE the ownership flip (never guessed). It reads with
#      row_security=off, so it needs a BYPASSRLS read-only auditor connection: set
#      DECISION_SOR_AUDIT_DATABASE_URL. Without it the verifier uses DATABASE_URL and an RLS-bound
#      role fails loudly rather than reporting an empty quarantine.
#
# Optional: PYTHON (interpreter that has asyncpg; default "python").
#
# It does NOT set DECISION_SERVICE_SOR_ENABLED and does NOT flip ownership — that stays an explicit
# operator action after every gate is green (see the production promotion runbook).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNNER="$REPO_ROOT/services/decision-service/migration_runner.py"
BACKFILL="$REPO_ROOT/services/decision-service/backfill.py"
PYTHON_BIN="${PYTHON:-python}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "::error:: DATABASE_URL is required (decision schema-owner/migrator role, not superuser/BYPASSRLS, not an app role)" >&2
  exit 2
fi
if [[ "${DECISION_SERVICE_ALLOW_SCHEMA_CHANGE:-}" != "true" ]]; then
  echo "::error:: refusing to apply schema: set DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true to proceed" >&2
  exit 2
fi

echo "== decision-service migrate: pre-apply --check =="
pre_rc=0
"$PYTHON_BIN" "$RUNNER" --check || pre_rc=$?
if [[ "$pre_rc" -eq 2 ]]; then
  echo "(pending migrations present — expected before first apply)"
elif [[ "$pre_rc" -ne 0 ]]; then
  echo "::error:: pre-apply --check failed (exit $pre_rc) for a reason other than pending migrations — fix the connection, credentials or interpreter before applying" >&2
  exit "$pre_rc"
fi

echo "== decision-service migrate: --apply =="
"$PYTHON_BIN" "$RUNNER" --apply

echo "== decision-service migrate: post-apply --check (must be clean) =="
"$PYTHON_BIN" "$RUNNER" --check

echo "== WX-10.7 review parity / quarantine (read-only; resolve any quarantined rows before cutover) =="
DATABASE_URL="${DECISION_SOR_AUDIT_DATABASE_URL:-$DATABASE_URL}" "$PYTHON_BIN" "$BACKFILL" --verify-review

echo "decision_service_migrate_ok"
