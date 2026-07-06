# Sahool — Backfill Runtime UI Sync + RLS Automation Fix

Date: 2026-07-06
Base ZIP: `sahool_main_fe9caca_compose_env_contract_fixed.zip`
Output ZIP: `sahool_main_fe9caca_backfill_runtime_ui_sync_fixed.zip`

## Executive result

Implemented the remaining fixes after the compose/env/MinIO work:

1. Frontend no longer stops after receiving `run_id` from historical imagery backfill.
2. Sahool Platform now exposes a tenant-scoped status proxy for `GET /api/v1/fields/{field_id}/imagery/backfill/{run_id}`.
3. MapHub polls the run status until terminal state and refreshes `available-dates`, Timeline, and raster tile cache timestamp.
4. `imagery_automation_fields` writes now set `app.current_tenant` inside a transaction before RLS-protected INSERT/UPDATE, avoiding the previous policy violation path without BYPASSRLS.
5. Added CI/static contract gate to prevent regressions.

## Changed files

- `frontend/src/services/api.ts`
  - Added `HistoricalImageryBackfillStatus`.
  - Added `isTerminalBackfillStatus()`.
  - Added `fetchHistoricalImageryBackfillStatus(fieldId, runId)` using platform proxy.

- `frontend/src/sections/MapHub.tsx`
  - After async `run_id`, polls status up to 80 attempts.
  - Refreshes available dates/timeline during processing and on terminal state.
  - Shows honest progress: persisted / failed / skipped counts.
  - Emits success/warning/error toast based on final status.

- `services/sahool-platform/api/routers/fields.py`
  - Added platform proxy:
    - `GET /api/v1/fields/{field_id}/imagery/backfill/{run_id}`
  - Checks tenant-owned field in platform DB.
  - Injects `X-Agent-Token` and `X-Tenant-Id` to raster-service.

- `services/sahool-platform/api/imagery_automation.py`
  - Added `_set_tenant_context_if_any()` helper.
  - `_persist_field()`, `_persist_ndvi()`, `_persist_spectral()` now wrap writes in a transaction and call `set_config('app.current_tenant', tenant_id, true)` before writing.

- `frontend/src/services/api.test.ts`
  - Added status proxy API test.
  - Added terminal status helper test.

- `scripts/ci/backfill_ui_sync_gate.py`
  - New CI gate validating the cross-layer contract.

- `.github/workflows/ci.yml`
  - Runs `backfill-ui-sync-gate`.

## Verification run here

Passed:

```bash
python3 -m py_compile \
  scripts/ci/backfill_ui_sync_gate.py \
  scripts/ci/compose_env_contract_gate.py \
  scripts/ci/minio_s3_contract_gate.py \
  services/sahool-platform/api/routers/fields.py \
  services/sahool-platform/api/imagery_automation.py

python3 scripts/ci/backfill_ui_sync_gate.py
python3 scripts/ci/compose_env_contract_gate.py
python3 scripts/ci/minio_s3_contract_gate.py
python3 scripts/ci/service_port_gate.py
python3 scripts/ci/nginx_compose_dns_gate.py

python3 - <<'PY'
import yaml
for p in ['docker-compose.v9.yml','docker-compose.fixed.yml','.github/workflows/ci.yml']:
    yaml.safe_load(open(p, encoding='utf-8'))
    print('YAML OK', p)
PY
```

Results:

```text
backfill-ui-sync contract: OK
compose-env contract: OK
checked 10 compose files, 186 env keys, 165 compose references
MinIO/S3 credential and storage contract is consistent
service-port-gate: PASS
nginx-compose-dns-gate: PASS (15 upstreams)
YAML OK docker-compose.v9.yml
YAML OK docker-compose.fixed.yml
YAML OK .github/workflows/ci.yml
```

## What still needs local runtime validation

Docker is unavailable in this execution environment, so run locally:

```bash
docker compose -f docker-compose.v9.yml config >/tmp/sahool-compose-rendered.yml
docker compose -f docker-compose.v9.yml up -d --force-recreate \
  sahool-platform sahool-raster-service sahool-raster-backfill-scan-worker sahool-minio sahool-titiler
```

Then trigger a backfill and verify polling:

```bash
curl -X POST "http://127.0.0.1/api/v1/fields/fld_f139e9d065e1/imagery/backfill" \
  -H "Content-Type: application/json" \
  -d '{"months":3,"indices":["truecolor","ndvi","ndmi"],"max_cloud_pct":50,"limit_per_month":8,"apply_cloud_mask":true}'
```

Open MapHub and verify the status changes from planned/searching/processing to completed/completed_with_errors/failed, and that Timeline updates without manual refresh.
