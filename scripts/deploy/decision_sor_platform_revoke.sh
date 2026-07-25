#!/usr/bin/env bash
# DB-level revoke/restore of platform write access on the decision SoR tables — cutover-time,
# reversible, out-of-band operator step. The single supported entry point.
#
# This is the complementary DB-level enforcement for the app-layer guard
# (sahool-platform decision_sor_mode.assert_platform_may_write_decision_sor). It strips
# INSERT/UPDATE/DELETE (keeps SELECT) from the platform role on the FIVE platform-owned SoR
# tables, so a platform write is denied at the database even if the Python guard is bypassed.
#
# SAME-DB topology only: in the split-DB topology the platform has no grant on the decision
# database, so this is a no-op there and need not be run.
#
#   revoke   : REVOKE at cutover — requires DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true
#              AND DECISION_SOR_ALLOW_PLATFORM_REVOKE=true (fail-closed).
#   rollback : GRANT back (exact inverse) — requires DECISION_SERVICE_ROLLBACK_APPROVED=true
#              AND DECISION_SOR_ALLOW_PLATFORM_REVOKE=true.
#
# It does NOT flip SAHOOL_DECISION_WRITE_MODE or any SoR flag — ownership demotion stays an
# explicit operator action (see docs/runbooks/DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNNER="$REPO_ROOT/services/decision-service/platform_sor_revoke.py"

MODE="${1:-}"
if [[ "$MODE" != "revoke" && "$MODE" != "rollback" ]]; then
  echo "usage: $0 {revoke|rollback}" >&2
  exit 2
fi

if [[ -z "${DECISION_SOR_ADMIN_DATABASE_URL:-}" ]]; then
  echo "::error:: DECISION_SOR_ADMIN_DATABASE_URL is required (table-owner/superuser role, not the platform app role)" >&2
  exit 2
fi
if [[ -z "${DECISION_SOR_PLATFORM_ROLE:-}" ]]; then
  echo "::error:: DECISION_SOR_PLATFORM_ROLE is required (the platform app role to revoke writes from, e.g. sahool_app)" >&2
  exit 2
fi

echo "== platform SoR revoke: pre-action --check =="
python "$RUNNER" --check

if [[ "$MODE" == "revoke" ]]; then
  echo "== platform SoR revoke: --revoke (cutover-gated) =="
  python "$RUNNER" --revoke
else
  echo "== platform SoR revoke: --grant (rollback-gated) =="
  python "$RUNNER" --grant
fi

echo "decision_sor_platform_${MODE}_ok"
