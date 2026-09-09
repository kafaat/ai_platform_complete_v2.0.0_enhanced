#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${1:-$PWD}"
[[ "${ALLOW_LIVE_READONLY:-NO}" == "YES" ]] || {
  printf 'Refusing: set ALLOW_LIVE_READONLY=YES\n' >&2
  exit 2
}
: "${ENV_FILE:?trusted ENV_FILE is required}"
[[ -f "$ENV_FILE" ]] || {
  printf 'Refusing: ENV_FILE not found\n' >&2
  exit 2
}

: "${COMPOSE_FILE:=docker-compose.v9.yml}"
: "${COMPOSE_PROJECT_NAME:=sahool-live-gap}"
: "${ENVIRONMENT_ID:=local-live-isolated}"
: "${PLATFORM_URL:=http://127.0.0.1:8000}"
: "${DECISION_URL:=http://127.0.0.1:8160}"
: "${POSTGRES_SERVICE:=sahool-postgres}"
: "${POSTGRES_DB:=sahool}"
: "${POSTGRES_USER:=sahool_user}"
: "${NATS_SERVICE:=sahool-nats}"

cd "$REPO"
[[ -z "$(git status --porcelain)" ]] || {
  printf 'Refusing unclaimable evidence from a dirty worktree\n' >&2
  exit 2
}
SUBJECT_SHA="$(git rev-parse HEAD)"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-$(dirname "$REPO")/sahool-live-evidence}"
EV="$EVIDENCE_ROOT/$SUBJECT_SHA/$RUN_ID"
mkdir -p "$EV"
COMMANDS="$EV/commands.tsv"
printf 'started_utc\tname\texit_code\tcommand\n' > "$COMMANDS"

compose() {
  docker compose --env-file "$ENV_FILE" -p "$COMPOSE_PROJECT_NAME" \
    -f "$COMPOSE_FILE" "$@"
}

capture() {
  local name="$1"
  shift
  local started rc rendered
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf -v rendered '%q ' "$@"
  if "$@" >"$EV/$name.out" 2>"$EV/$name.err"; then rc=0; else rc=$?; fi
  printf '%s\t%s\t%s\t%s\n' "$started" "$name" "$rc" "$rendered" >> "$COMMANDS"
}

http_get() {
  python - "$1" <<'PY'
import sys
import urllib.error
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=15) as response:
        print(f"http_code={response.status}")
        print(response.read().decode("utf-8", errors="replace"))
except urllib.error.HTTPError as exc:
    print(f"http_code={exc.code}")
    print(exc.read().decode("utf-8", errors="replace"))
    raise SystemExit(1)
except Exception as exc:
    print(f"transport_error={type(exc).__name__}:{exc}")
    raise SystemExit(2)
PY
}

git show --no-patch --format=fuller HEAD > "$EV/00_git_identity.txt"
capture 01_compose_ps compose ps
capture 02_compose_images compose images --format json
capture 03_generated python scripts/ci/verify_all_generated.py --check
capture 04_evidence_guard python scripts/ci/production_evidence_pack_guard.py --check
capture 05_pcert python scripts/ci/production_certification_blockers_status.py --require-certified
capture 06_platform_ready http_get "$PLATFORM_URL/readyz"
capture 07_decision_ready http_get "$DECISION_URL/readyz"
capture 08_cutover http_get "$DECISION_URL/v1/cutover/readiness"
capture 09_roles compose exec -T "$POSTGRES_SERVICE" \
  psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles ORDER BY rolname;"
capture 10_ledger compose exec -T "$POSTGRES_SERVICE" \
  psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT outcome, count(*) AS total FROM execution_ledger GROUP BY outcome ORDER BY outcome;"
capture 11_nats_security_flags compose exec -T "$NATS_SERVICE" sh -c '
  cfg=/etc/nats/nats.conf
  test -r "$cfg" || exit 2
  for key in authorization users permissions token password; do
    if grep -Eiq "(^|[[:space:]{])${key}[[:space:]]*[:=]?" "$cfg"; then
      printf "%s_present=true\n" "$key"
    else
      printf "%s_present=false\n" "$key"
    fi
  done
'
capture 12_nats_varz compose exec -T "$NATS_SERVICE" \
  wget -qO- http://127.0.0.1:8222/varz

{
  printf 'subject_sha=%s\n' "$SUBJECT_SHA"
  printf 'environment_id=%s\n' "$ENVIRONMENT_ID"
  printf 'runtime_verified=false\nproduction_certified=false\n'
  printf 'note=read-only baseline; no NATS publish and no database writes\n'
} > "$EV/STATUS.txt"

find "$EV" -type f -print0 | sort -z | xargs -0 sha256sum > "$EV.sha256"
sha256sum -c "$EV.sha256"
printf 'READONLY_BASELINE_COMPLETE\nevidence=%s\nmanifest=%s\n' "$EV" "$EV.sha256"
