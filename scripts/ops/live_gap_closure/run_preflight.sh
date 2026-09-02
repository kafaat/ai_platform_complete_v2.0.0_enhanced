#!/usr/bin/env bash
set -Eeuo pipefail

BASE_SHA="${BASE_SHA:-9b1f630b42044d8516c6420c5139cfcf901e2b95}"
REPO="${1:-$PWD}"
MODE="${MODE:-static}"

fail() {
  printf 'PRECHECK_FAIL: %s\n' "$*" >&2
  exit 2
}

cd "$REPO"
for cmd in git python rg; do
  command -v "$cmd" >/dev/null || fail "$cmd not found"
done

SUBJECT_SHA="$(git rev-parse HEAD)"
git merge-base --is-ancestor "$BASE_SHA" "$SUBJECT_SHA" || \
  fail "subject $SUBJECT_SHA is not descended from baseline $BASE_SHA"
[[ -z "$(git status --porcelain)" ]] || \
  fail "worktree is dirty; preserve the changes and run after commit/review"

python -c 'import jsonschema, pytest' >/dev/null 2>&1 || \
  fail "install tests_v9/requirements-test.txt in an isolated Python environment"

required=(
  docs/runbooks/LIVE_GAP_CLOSURE_AGENT_RUNBOOK.md
  scripts/ci/verify_all_generated.py
  scripts/ci/production_evidence_pack_guard.py
  scripts/ci/production_certification_blockers_status.py
  services/decision-service/decision_sor_role_certify.py
  scripts/architecture/s5_decision_live_closure_receipt.py
  tests_v9/test_live_gap_closure_runbook_contract.py
)
for path in "${required[@]}"; do
  [[ -f "$path" ]] || fail "required legal path missing: $path"
done

if [[ "$MODE" == "live" ]]; then
  : "${ENV_FILE:?ENV_FILE required in live mode}"
  : "${COMPOSE_FILE:=docker-compose.v9.yml}"
  : "${COMPOSE_PROJECT_NAME:=sahool-live-gap}"
  [[ -f "$ENV_FILE" ]] || fail "ENV_FILE not found"
  command -v docker >/dev/null || fail "docker not found"
  docker info >/dev/null 2>&1 || fail "Docker daemon unavailable"
  docker compose --env-file "$ENV_FILE" -p "$COMPOSE_PROJECT_NAME" \
    -f "$COMPOSE_FILE" config --quiet || fail "compose config invalid"
elif [[ "$MODE" != "static" ]]; then
  fail "MODE must be static or live"
fi

printf 'PRECHECK_OK\n'
printf 'base_sha=%s\nsubject_sha=%s\nmode=%s\n' "$BASE_SHA" "$SUBJECT_SHA" "$MODE"
