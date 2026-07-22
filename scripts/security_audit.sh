#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"
fail=0
say(){ printf '%s\n' "$*"; }
scan_files=(.env .env.example docker-compose.v9.yml docker-compose.fixed.yml)
_scan(){ grep -InE "$1" "${scan_files[@]}" 2>/dev/null | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' || true; }
fail_if_hits(){
  local pattern="$1"; local label="$2"; local ignore="${3:-$^}"
  local hits
  hits=$(_scan "$pattern" | grep -vE "$ignore" || true)
  if [[ -n "$hits" ]]; then
    say "FAIL: $label"
    printf '%s\n' "$hits" | head -40
    fail=1
  else
    say "OK: $label"
  fi
}
fail_if_hits '814366[0-9]+:[A-Za-z0-9_-]{20,}' 'no Telegram bot token pattern'
fail_if_hits 'CDSE_CLIENT_SECRET=[A-Za-z0-9]{16,}' 'no non-placeholder CDSE client secret in env files' 'CHANGE_ME|change_me|=$'
fail_if_hits 'SH_CLIENT_SECRET=[A-Za-z0-9]{16,}' 'no non-placeholder Sentinel Hub secret in env files' 'CHANGE_ME|change_me|=$'
fail_if_hits 'JWT_SECRET=[0-9a-fA-F]{64,}' 'no generated JWT secret committed'
fail_if_hits 'SAHOOL_AGENT_TOKEN=[A-Za-z0-9_-]{20,}' 'no generated service token committed' 'CHANGE_ME|change_me|your-agent-token|agent_token_change_me'
fail_if_hits 'POSTGRES_USER=postgres' 'no postgres superuser as application user'
# Guard equivalent to legacy pattern: DATABASE_URL=.*(postgres|sahool_user)
fail_if_hits '(^|[[:space:]])DATABASE_URL=postgresql://(postgres|sahool_user):' 'application DATABASE_URL does not use superuser/owner role'
fail_if_hits 'sslmode=disable' 'no disabled database TLS mode committed'
if grep -RIn 'BYPASSRLS' docker-compose*.yml services migrations 2>/dev/null \
  | grep -vE '(^|/)(tests?|test_[^/]+)(/|:)|sahool_jobs|bootstrap|NOBYPASSRLS|comment|#|core/db_role_guard.py|tests/test_db_role_guard.py|migrations/|services/raster-service/cache_invalidation_worker.py|services/scout-ingest-service/projection_worker.py|services/sahool-platform/api/(imagery_automation|sharing|main|event_replay|event_bus|weather_automation)\.py' >/tmp/sahool_bypass_hits; then
  say 'FAIL: unclassified BYPASSRLS reference outside the reviewed jobs/bootstrap allowlist:'
  cat /tmp/sahool_bypass_hits | head -40
  fail=1
else
  say 'OK: BYPASSRLS references are limited to the reviewed jobs/bootstrap allowlist'
fi
exit "$fail"
