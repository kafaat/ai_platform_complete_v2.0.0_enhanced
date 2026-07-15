#!/usr/bin/env bash
# field-management-service — staging LIVE gate (real PostgreSQL + running service).
#
# The CI unit/structural gates prove the CONTRACT statically. This gate proves the
# two hypotheses CI cannot, against a live DB on the SAME commit that CI validated:
#   • cross-tenant lookup returns 404 under RLS (no disclosure)
#   • a reused connection does NOT leak the tenant GUC (set_config transaction-local)
#
# Run this on the exact CI-green SHA (e.g. 4c2559b) BEFORE fast-forwarding main/develop.
# It NEVER prints the token; pass secrets via env, not argv.
#
# Required env:
#   EXPECTED_SHA          the CI-green commit this gate must run on (full or short prefix).
#                         The gate REFUSES to run on any other checkout — the tested code
#                         must equal the code to be merged.
#   DATABASE_URL          postgresql://sahool_app:...@host:5432/sahool   (NOBYPASSRLS role)
#   SAHOOL_AGENT_TOKEN    the service token the field owner expects
#   FIELD_SERVICE_URL     base URL of a RUNNING field-management-service (e.g. http://127.0.0.1:8099)
#   TENANT_A TENANT_B     two distinct tenant uuids (owner + spoofed)
#   FIELD_A               a field_id owned by TENANT_A (seed it first)
#
# Exit 0 = all acceptance checks EXECUTED and passed; non-zero = a gate failed OR a check
# could not actually run (skipped/missing). A skipped isolation test is a FAILURE, not a pass.
set -euo pipefail

fail() { echo "GATE FAIL: $*" >&2; exit 1; }
pass() { echo "  ok  - $*"; }

: "${EXPECTED_SHA:?EXPECTED_SHA (the CI-green commit) required — the gate must be pinned to a SHA}"
: "${DATABASE_URL:?DATABASE_URL (sahool_app) required}"
: "${SAHOOL_AGENT_TOKEN:?SAHOOL_AGENT_TOKEN required}"
: "${FIELD_SERVICE_URL:?FIELD_SERVICE_URL of a running field-management-service required}"
: "${TENANT_A:?TENANT_A uuid required}"; : "${TENANT_B:?TENANT_B uuid required}"; : "${FIELD_A:?FIELD_A id required}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SVC="X-Service-Name: vegetation-analysis-service"
TOK="X-Agent-Token: ${SAHOOL_AGENT_TOKEN}"

echo "== 0) SHA pin — tested code must equal merge candidate =="
actual_sha="$(git -C "$ROOT" rev-parse HEAD)"
case "$actual_sha" in
  "${EXPECTED_SHA}"*) pass "HEAD $actual_sha matches EXPECTED_SHA=$EXPECTED_SHA" ;;
  *) fail "SHA mismatch: expected=$EXPECTED_SHA actual=$actual_sha (run the gate on the CI-green SHA)" ;;
esac

echo "== 1) RLS role is NOT superuser / BYPASSRLS =="
role_flags="$(psql "$DATABASE_URL" -tAc \
  "SELECT rolsuper::text||','||rolbypassrls::text FROM pg_roles WHERE rolname = current_user")"
[ "$role_flags" = "false,false" ] || fail "app role is superuser/bypassrls ($role_flags) — RLS would be vacuous"
pass "current_user is NOSUPERUSER + NOBYPASSRLS"

echo "== 2) set_config(...,true) is transaction-local in the service source =="
grep -q "set_config('app.current_tenant', \$1, true)" "$ROOT/services/field-management-service/main.py" \
  || fail "service does not use transaction-local set_config"
grep -q "create_pool" "$ROOT/services/field-management-service/main.py" \
  && fail "service caches a pool (cross-request tenant-leak risk)" || pass "per-request connection, transaction-local GUC"

echo "== 3) live RLS isolation (pytest integration: spoofed-tenant 404 + connection-reuse) =="
# Capture the summary — a SKIPPED test (no live DB) must NOT count as a pass. The gate
# fails unless the isolation test actually EXECUTED (>=1 passed, 0 skipped).
iso_out="$(cd "$ROOT/services/field-management-service" && python3 -m pytest tests/ -m integration -q 2>&1)" \
  || { echo "$iso_out" | tail -5 >&2; fail "live PostgreSQL isolation test failed"; }
echo "$iso_out" | tail -2
echo "$iso_out" | grep -qE "[1-9][0-9]* passed" \
  || fail "isolation test did not execute (skipped/none) — a live sahool_app DB is required"
echo "$iso_out" | grep -qE "[0-9]+ skipped" \
  && fail "isolation test was SKIPPED (missing DB/env) — a skip is not a pass for a live gate"
pass "cross-tenant read 404 + connection-reuse isolation actually executed under RLS"

echo "== 4) HTTP contract against the running field owner =="
code() { curl -sS -o /dev/null -w '%{http_code}' "$@"; }
c200="$(code -H "$TOK" -H "$SVC" -H "X-Tenant-Id: $TENANT_A" "$FIELD_SERVICE_URL/internal/fields/$FIELD_A")"
[ "$c200" = 200 ] || fail "valid token + owner tenant + valid field expected 200, got $c200"; pass "valid → 200"
c404="$(code -H "$TOK" -H "$SVC" -H "X-Tenant-Id: $TENANT_B" "$FIELD_SERVICE_URL/internal/fields/$FIELD_A")"
[ "$c404" = 404 ] || fail "spoofed tenant expected 404, got $c404"; pass "spoofed tenant → 404"
c401m="$(code -H "$SVC" -H "X-Tenant-Id: $TENANT_A" "$FIELD_SERVICE_URL/internal/fields/$FIELD_A")"
[ "$c401m" = 401 ] || fail "missing service token expected 401, got $c401m"; pass "missing token → 401"
c401w="$(code -H "X-Agent-Token: wrong-token" -H "X-Tenant-Id: $TENANT_A" "$FIELD_SERVICE_URL/internal/fields/$FIELD_A")"
[ "$c401w" = 401 ] || fail "wrong service token expected 401, got $c401w"; pass "wrong token → 401"

echo "== 5) audit trail (no secret printed) =="
printf '{"commit_sha":"%s","tenant_a":"%s","tenant_b":"%s","field_id":"%s","field_owner_200":%s,"cross_tenant_404":%s,"missing_token_401":%s,"wrong_token_401":%s,"service_name":"vegetation-analysis-service"}\n' \
  "$(git -C "$ROOT" rev-parse --short HEAD)" "$TENANT_A" "$TENANT_B" "$FIELD_A" "$c200" "$c404" "$c401m" "$c401w"

echo "field_management_live_gate_ok"
