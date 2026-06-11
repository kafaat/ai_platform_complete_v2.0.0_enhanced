# SAHOOL Alerting — condition-gated receivers

Real alert delivery (Slack / email / Telegram) is **off by default**. The stack
ships with a base no-op AlertManager config so a fresh deployment never spams a
non-existent endpoint and never produces delivery failures. Real receivers turn
on **only** once their secrets are provisioned.

## The gate

The activation condition mirrors `capabilities.alerting_receivers_active()`:

> alerting is **active** when **any** of these env vars is set:
> `ALERT_SLACK_WEBHOOK`, `ALERT_SMTP_HOST`, `ALERT_TELEGRAM_TOKEN`.

If none are set, alerting is **dormant** — `monitoring/alertmanager.yml` (route →
`null` no-op receiver) stays in use. Silent, by design.

## Files

| File | Role |
|------|------|
| `alertmanager.yml` | Base **no-op** config. Mounted by default. Route → `null`. |
| `alertmanager.overlay.example.yml` | Worked example with **real** receivers + severity routes. Uses `__PLACEHOLDER__` tokens — **no secrets**. |
| `render-alertmanager.sh` | Gate + renderer. Substitutes `__VAR__` placeholders from env → `alertmanager.rendered.yml`. No-op (exit 0) when dormant. |
| `alertmanager.rendered.yml` | **Generated**, contains live secrets. Do **not** commit (add to `.gitignore`). |

## Routing (overlay)

- `critical` → **all channels** (Slack + email + Telegram), `group_wait` 10s, resend hourly.
- `warning` → **Slack only**, default cadence.
- Warning alerts are inhibited while a `critical` for the same `alertname`+`job` fires.

## How to activate

1. **Provision secrets** (env / secret store — never commit them):

   ```sh
   export ALERT_SLACK_WEBHOOK='https://hooks.slack.com/services/XXX/YYY/ZZZ'
   # optional email channel:
   export ALERT_SMTP_HOST='smtp.example.com:587'
   export ALERT_SMTP_FROM='alerts@sahool.example'
   export ALERT_SMTP_TO='ops@sahool.example'
   export ALERT_SMTP_USER='alerts@sahool.example'
   export ALERT_SMTP_PASS='********'
   # optional Telegram channel:
   export ALERT_TELEGRAM_TOKEN='123456:ABC-DEF...'
   export ALERT_TELEGRAM_CHAT_ID='-1001234567890'
   ```

2. **Render**:

   ```sh
   sh monitoring/render-alertmanager.sh
   ```

   - Secrets present → writes `monitoring/alertmanager.rendered.yml` (mode 600).
   - No secrets → prints `alerting receivers dormant — base no-op config in use`
     and exits 0 without writing anything.

3. **Point the AlertManager service at the rendered file.** In
   `docker-compose.v9.yml`, the `sahool-alertmanager` service mounts the base
   config:

   ```yaml
   - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
   ```

   To go live, mount the rendered overlay instead (e.g. via a compose override
   file so the base commit stays untouched):

   ```yaml
   # docker-compose.override.yml
   services:
     sahool-alertmanager:
       volumes:
         - ./monitoring/alertmanager.rendered.yml:/etc/alertmanager/alertmanager.yml:ro
   ```

   Then `docker compose up -d sahool-alertmanager` to reload.

## Why an overlay (not env interpolation)

AlertManager does **not** expand environment variables in its config natively.
The clean pattern is therefore a rendered overlay mounted **instead of** the base
when secrets exist — keeping the committed config secret-free and the default a
silent no-op.

## Safety notes

- `alertmanager.overlay.example.yml` holds **placeholders only** — safe to commit.
- `alertmanager.rendered.yml` holds **live secrets** — gitignore it; it is written
  with `600` perms; the render script never echoes secret values.
- Default behavior = **no delivery, no failures, no noise.**
