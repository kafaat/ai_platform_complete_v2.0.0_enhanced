#!/bin/sh
# render-alertmanager.sh — CONDITION-GATED renderer for SAHOOL AlertManager.
#
# Gate (mirrors capabilities.alerting_receivers_active()): real receivers are
# rendered ONLY when at least one alerting secret is provisioned —
#   ALERT_SLACK_WEBHOOK | ALERT_SMTP_HOST | ALERT_TELEGRAM_TOKEN
# Otherwise this is a no-op: it prints the dormant message and exits 0, leaving
# the base no-op config (monitoring/alertmanager.yml) in use. No delivery, no
# failures, no noise.
#
# Idempotent. Safe: set -eu, never echoes secret values.
#
# Usage:   sh monitoring/render-alertmanager.sh
# Output (only when gated ON): monitoring/alertmanager.rendered.yml

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OVERLAY="$SCRIPT_DIR/alertmanager.overlay.example.yml"
RENDERED="$SCRIPT_DIR/alertmanager.rendered.yml"

# --- GATE ------------------------------------------------------------------
if [ -z "${ALERT_SLACK_WEBHOOK:-}" ] \
   && [ -z "${ALERT_SMTP_HOST:-}" ] \
   && [ -z "${ALERT_TELEGRAM_TOKEN:-}" ]; then
  echo "alerting receivers dormant — base no-op config in use"
  exit 0
fi

# --- RENDER ----------------------------------------------------------------
if [ ! -f "$OVERLAY" ]; then
  echo "render-alertmanager: missing overlay template: $OVERLAY" >&2
  exit 1
fi

# Replace a __PLACEHOLDER__ with the value of an env var, escaping sed-special
# chars (& / \) in the replacement. Never prints the value.
_sub() {
  _val=$(printf '%s' "$(eval "printf '%s' \"\${$2:-}\"")" | sed -e 's/[&/\\]/\\&/g')
  sed "s/$1/$_val/g"
}

cat "$OVERLAY" \
  | _sub '__ALERT_SLACK_WEBHOOK__'    ALERT_SLACK_WEBHOOK \
  | _sub '__ALERT_SMTP_HOST__'        ALERT_SMTP_HOST \
  | _sub '__ALERT_SMTP_FROM__'        ALERT_SMTP_FROM \
  | _sub '__ALERT_SMTP_TO__'          ALERT_SMTP_TO \
  | _sub '__ALERT_SMTP_USER__'        ALERT_SMTP_USER \
  | _sub '__ALERT_SMTP_PASS__'        ALERT_SMTP_PASS \
  | _sub '__ALERT_TELEGRAM_TOKEN__'   ALERT_TELEGRAM_TOKEN \
  | _sub '__ALERT_TELEGRAM_CHAT_ID__' ALERT_TELEGRAM_CHAT_ID \
  > "$RENDERED.tmp"

chmod 600 "$RENDERED.tmp"
mv "$RENDERED.tmp" "$RENDERED"

echo "alerting receivers active — rendered: $RENDERED"
