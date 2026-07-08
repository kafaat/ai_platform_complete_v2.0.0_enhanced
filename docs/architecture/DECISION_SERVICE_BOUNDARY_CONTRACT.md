# Decision / Outcome / Learning Boundary Contract

## Status: INTERIM BRIDGE (temporary — NOT the final architecture)

The P4.5–P4.7 extraction pointed the platform's decision/outcome/learning writes at
`decision-service`, but `decision-service` has **no datastore** — it was silently dropping
data and returning a fake `persisted: true`. Until `decision-service` becomes a real
system-of-record, we run a **temporary dual-path bridge**:

- **`sahool-platform` = temporary Source of Record (SoR).** It performs the **authoritative**
  loop-table DB write (`tenant_connection` + `INSERT` [+ `_emit_domain_event` outbox]). The
  request only returns success if this platform write succeeds (fail-closed, exactly like the
  pre-extraction behavior). No data is lost if `decision-service` is down.
- **`decision-service` = best-effort, non-authoritative mirror (NOT yet the SoR).** After the
  authoritative platform write, each write path best-effort mirrors to `decision-service`
  through `api/decision_service_client.py`. The mirror call is wrapped so a mirror failure is
  **logged and observable but never fails the user request** and never loses platform data.
- The `decision-service` stub is **honest**: its write endpoints return
  `{"accepted": true, "authoritative": false, "persisted": false, "note": "mirror-only; …"}`.
  It never claims real persistence.

## Loop tables (authoritative writer = `sahool-platform`, mirror = `decision-service`)
- `decision_record`
- `dispatch_decisions`
- `outcome_record`
- `recommendation_outcomes`
- `online_learning_updates`
- `recommendation_feedback` remains deprecated and has no runtime writer.

`db_ownership.yml` records these tables as `owner: sahool-platform`,
`writers: [sahool-platform]`, `mirror: decision-service`, `status: interim-bridge`.

## Interim write-path shape (per converted route)
```
request → platform router
        → platform AUTHORITATIVE DB write (must succeed first; 503 on failure)
        → best-effort mirror to decision-service (try/except; never raises)
        → success response derived ONLY from the platform write
```
Authoritative writers (temporary SoR): `api/routers/decision_record.py`,
`api/routers/decision_dispatch.py`, `api/routers/recommendations.py`,
`api/phase_runtime_store.py`, `api/routers/weather.py`.

## Interim read-path shape
Loop **reads** (`learning/summary`, `decision/{id}/lineage`, `decision/records`,
`field/{id}/lineage`) read the platform loop tables **authoritatively** again — delegating
reads to the not-yet-SoR `decision-service` returned empty data.

## Rules
1. A decision write must never return success unless the platform DB write succeeded.
2. Learning updates without source lineage are still rejected/marked `rejected_untraceable`;
   `resolve_learning_source` runs before the authoritative write; a learning update is never
   silently trusted.
3. Outcome reconciliation keeps reading both `outcome_record` and `recommendation_outcomes`.
4. The mirror transport (`X-Tenant-Id` / `X-Agent-Token` forwarding) stays centralized in
   `api/decision_service_client.py`.
5. `decision-service` write endpoints must never return `persisted: true` (mirror sink only).

## History (superseded by the interim bridge)
- P4.1 Decision Service Contract and runtime skeleton.
- P4.2 Outcome Service Contract and write endpoint.
- P4.3 Learning Summary / Learning Update Facade.
- P4.4 DB Ownership Guard for loop tables.
- P4.5–P4.7 converted platform write/read paths to facade-only. **Rescoped by this bridge:**
  the platform re-becomes the authoritative writer; `decision-service` is a best-effort mirror.

## Migration path to a future `decision-service` SoR

### ⚠️ Schema prerequisite discovered 2026-07-08 (blocks any additive dual-write)
Making `decision-service` *also* persist the loop tables (an additive, flag-gated mirror that
writes alongside the platform) is **only safe for tables with a natural dedup key**, because the
mirror runs *after* the platform's authoritative write and must be a no-op on the already-written
row (`ON CONFLICT DO NOTHING`). Per-table status (verified against migrations + platform INSERTs):
- `decision_record` — PK `decision_id` ✅ dedup-able.
- `dispatch_decisions` — PK `decision_id` ✅ dedup-able.
- `outcome_record` — PK `outcome_id` + `UNIQUE ux_outcome_record_idem(idempotency_key)` ✅.
- `online_learning_updates` — `UNIQUE (tenant_id, update_id)` ✅ dedup-able.
- **`recommendation_outcomes` — ❌ NOT dedup-able.** PK is `BIGSERIAL outcome_id` and the platform
  INSERT (`services/sahool-platform/api/routers/recommendations.py:347`) has **no `ON CONFLICT`**,
  so every call appends a fresh row. A mirror that also persisted this write would create a
  **duplicate outcome row** for one real-world outcome → pseudoreplication that inflates the
  learning sample and corrupts `success_rate` — exactly what `core/outcome_reconciler.py` and the
  loop-closure audit protect against.

**Therefore the SoR move must be a real cutover (platform stops writing → `decision-service`
becomes the sole writer), NOT an additive "both write" step.** Prerequisite before any flip:
a migration adds a natural dedup key to `recommendation_outcomes` (candidate
`UNIQUE (tenant_id, recommendation_id, season_id)` — first confirm the domain truly forbids
multiple outcome rows per (recommendation, season); if legitimate re-measurements exist, add an
explicit `idempotency_key` column instead). Design + verify on live Postgres (`-m integration`)
before any cutover — it cannot be done safely from a unit-only environment.

### Steps
1. Give `decision-service` a real datastore (Postgres + RLS + outbox), mirroring the loop
   schema; keep it accepting mirror writes (idempotent on `decision_id`/`idempotency_key`).
   **Prereq:** add the `recommendation_outcomes` dedup key above first.
2. Backfill from the platform SoR; run the mirror in shadow until row parity is verified.
3. Flip the authoritative write from platform → `decision-service` one table at a time
   (dual-write with `decision-service` authoritative, platform mirror), then
4. Demote the platform to a reader, update `db_ownership.yml` to
   `owner: decision-service`, and retire this interim bridge.
