# Phase 11 — Mobile Offline Sync Runtime Hardening

## Summary
This patch closes the remaining mobile/offline sync runtime gap by making sync operation IDs stable across retries, exposing a machine-readable sync manifest, adding a sync status endpoint, and binding the mobile AI Advisor to the real `ai_agronomist` runtime path.

## Implemented
- Added `api/offline_sync_contracts.py` as a pure contract/runtime layer.
- Added `GET /api/v1/sync/manifest`.
- Added `GET /api/v1/sync/status`.
- Preserved client supplied `op_id` / `operation_id` / `idempotency_key` inside `/api/v1/sync`.
- Kept legacy clients compatible when no client operation ID is supplied.
- Added conflict-aware metadata for `field.update` with optimistic row versioning.
- Updated mobile `ApiService.askAgent()` to call `/api/ai-agronomist/chat` instead of the older `/api/agent/query` path.
- Added mobile helpers for sync manifest, sync status and offline operation sync.
- Added `scripts/mobile/mobile_sync_smoke.sh`.
- Added migration `v112_mobile_offline_sync_runtime.sql` with RLS-hardened `mobile_sync_clients` and `mobile_sync_conflicts` tables.

## Safety Properties
- Fail-closed validation for malformed operation IDs.
- No direct DB/NATS exposure to mobile clients.
- `field.update` remains server-authoritative and conflict-aware.
- Legacy behavior remains available for older clients, but new clients can achieve cross-request idempotency.

## Runtime Validation Command
```bash
BASE_URL=http://localhost \
SAHOOL_JWT=<jwt> \
TENANT_ID=<tenant> \
./scripts/mobile/mobile_sync_smoke.sh
```
