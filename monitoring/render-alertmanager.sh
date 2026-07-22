#!/bin/sh
# render-alertmanager.sh — CONDITION-GATED renderer for SAHOOL AlertManager.
#
# Gate (mirrors capabilities.alerting_receivers_active()): real receivers are
# rendered ONLY when at least one alerting secret is provisioned —
#   ALERT_SLACK_WEBHOOK | ALERT_SMTP_HOST | ALERT_TELEGRAM_TOKEN
# Otherwise this is a no-op: prints the dormant message and exits 0, leaving the
# base no-op config (monitoring/alertmanager.yml) in use.
#
# IMPORTANT (review): it ASSEMBLES the config from ONLY the channels whose secrets
# are present — Slack-only provisioning yields a Slack-only receiver (no empty
# SMTP/Telegram blocks). So "any one channel is enough" always produces a VALID,
# usable config. (alertmanager.overlay.example.yml stays as a full reference.)
#
# Safe: set -eu, never echoes secret values. Output: monitoring/alertmanager.rendered.yml

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RENDERED="$SCRIPT_DIR/alertmanager.rendered.yml"

# --- GATE ------------------------------------------------------------------
if [ -z "${ALERT_SLACK_WEBHOOK:-}" ] \
   && [ -z "${ALERT_SMTP_HOST:-}" ] \
   && [ -z "${ALERT_TELEGRAM_TOKEN:-}" ]; then
  echo "alerting receivers dormant — base no-op config in use"
  exit 0
fi

TMP="$RENDERED.tmp"
: > "$TMP"

# --- global (SMTP transport only when email is provisioned) ----------------
{
  echo "global:"
  echo "  resolve_timeout: 5m"
  if [ -n "${ALERT_SMTP_HOST:-}" ]; then
    echo "  smtp_smarthost: '${ALERT_SMTP_HOST}'"
    echo "  smtp_from: '${ALERT_SMTP_FROM:-alerts@sahool.local}'"
    [ -n "${ALERT_SMTP_USER:-}" ] && echo "  smtp_auth_username: '${ALERT_SMTP_USER}'"
    [ -n "${ALERT_SMTP_PASS:-}" ] && echo "  smtp_auth_password: '${ALERT_SMTP_PASS}'"
    echo "  smtp_require_tls: true"
  fi
} >> "$TMP"

# --- route -----------------------------------------------------------------
{
  echo "route:"
  echo "  group_by: ['alertname', 'job', 'severity']"
  echo "  group_wait: 30s"
  echo "  group_interval: 5m"
  echo "  repeat_interval: 4h"
  echo "  receiver: 'sahool-receiver'"
  echo "  routes:"
  echo "    - matchers: [severity = \"critical\"]"
  echo "      receiver: 'sahool-receiver'"
  echo "      group_wait: 10s"
  echo "      repeat_interval: 1h"
} >> "$TMP"

# --- receivers (ONLY the channels whose secrets exist) ---------------------
{
  echo "receivers:"
  echo "  - name: 'sahool-receiver'"
  if [ -n "${ALERT_SLACK_WEBHOOK:-}" ]; then
    echo "    slack_configs:"
    echo "      - api_url: '${ALERT_SLACK_WEBHOOK}'"
    echo "        channel: '${ALERT_SLACK_CHANNEL:-#sahool-alerts}'"
    echo "        send_resolved: true"
    echo "        title: '[{{ .CommonLabels.severity }}] {{ .CommonLabels.alertname }}'"
  fi
  if [ -n "${ALERT_SMTP_HOST:-}" ] && [ -n "${ALERT_SMTP_TO:-}" ]; then
    echo "    email_configs:"
    echo "      - to: '${ALERT_SMTP_TO}'"
    echo "        send_resolved: true"
  fi
  if [ -n "${ALERT_TELEGRAM_TOKEN:-}" ] && [ -n "${ALERT_TELEGRAM_CHAT_ID:-}" ]; then
    echo "    telegram_configs:"
    echo "      - bot_token: '${ALERT_TELEGRAM_TOKEN}'"
    echo "        chat_id: ${ALERT_TELEGRAM_CHAT_ID}"
    echo "        parse_mode: 'HTML'"
    echo "        send_resolved: true"
  fi
} >> "$TMP"

# --- inhibit ---------------------------------------------------------------
{
  echo "inhibit_rules:"
  echo "  - source_matchers: [severity = \"critical\"]"
  echo "    target_matchers: [severity = \"warning\"]"
  echo "    equal: ['alertname', 'job']"
} >> "$TMP"

chmod 600 "$TMP"
mv "$TMP" "$RENDERED"
echo "alerting receivers active — rendered: $RENDERED (only provisioned channels)"
