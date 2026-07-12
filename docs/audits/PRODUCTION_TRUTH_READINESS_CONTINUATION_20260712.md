# SAHOOL Production Truth & Readiness Continuation — 2026-07-12

## Scope
Closed the remaining truthfulness gap between development-compatible vegetation/AgriAI behavior and production readiness.

## Changes
- Removed the dead synthetic vegetation timeseries generator.
- `/v1/timeseries/{field_id}` remains authoritative raster-only and never fabricates points.
- `/v1/ndvi/current/{field_id}` now reads the newest real raster-service observation; no synthetic current NDVI is created.
- Production (`VEGETATION_REAL_ONLY`) fails closed with HTTP 424 when authoritative NDVI is absent.
- Vegetation `/readyz` now depends on raster-service readiness in real-only mode.
- AgriAI `/readyz` now reports not-ready when `AGRIAI_PRODUCTION_MODE=1` and PCSE is unavailable.
- Corrected WOFOST documentation to match fail-closed production behavior.
- Corrected Decision runtime-work API documentation: side-effecting work uses durable leases.
- Added `scripts/ci/production_truth_readiness_gate.py`.
- Added focused regression tests and updated the obsolete synthetic-timeseries test.

## Verification
- Python compileall: PASS
- Existing agronomic/vegetation lineage gates: 8 PASS
- New production truth/readiness gate: PASS
- Focused suite: 36 passed, 1 skipped
- Skipped test: PostgreSQL integration requiring a real `DATABASE_URL`.

## Remaining external certification
- Live raster-service readiness and real Sentinel COG observations.
- PCSE installed and exercised with calibrated crop/soil/weather/agromanagement inputs.
- PostgreSQL migrations/triggers/RLS executed on a real database.

---

## Integration note (landed shape) — appended by the integrating session

This bundle stacked five delivered increments (AC-9 learning lineage → model-lifecycle
cohorts → runtime cohorts → terminal lineage → production truth/readiness). Landed as one
reconciled increment; deviations, each verified on real PostgreSQL:

1. **Migration renumbering + retargeting.** Delivered 021→024 landed as 020→023 (the
   bundle's 019/020 were reconciled earlier). The learning-lineage migration referenced the
   bundle's never-landed `decision_field_history_snapshots`; it now inherits/validates the
   landed `field_historical_context_snapshot_id` against
   `decision_field_historical_context_snapshots (tenant_id, historical_snapshot_id)`.
2. **RLS deviation (consistent with the landed 019 policy).** The delivered learning
   migration used `FORCE ROW LEVEL SECURITY` — untested in the bundle (its PostgreSQL proof
   was skipped) and unenforceable-yet-hazardous while the service connects as the table
   owner. Landed as ENABLE + tenant policy; FORCE arrives with the non-owner runtime role
   (operator cutover), as recorded for every other authoritative table.
3. **Real bug fixed in the delivered inheritance code:** asyncpg returns jsonb columns as
   JSON text; the bundle re-encoded inherited cohorts with `_json(...)`, double-encoding
   `{}` into the JSON *string* `"{}"` — every inheritance INSERT (13 sites) would have been
   rejected by the bundle's own lineage triggers on a real database. Landed with a
   `_cohorts_passthrough` helper; proven by the full decision-service battery.
4. **Existing runtime tests were re-grounded, not weakened:** orphan direct-seeds (rollout
   plans pointing at nonexistent receipts, retraining without monitoring, monitoring
   without an activated model) are now rejected by design; the tests seed an honest full
   activation chain via `tests/_model_chain.py` (evaluation → promotion → request → review
   → command → claim → activated receipt, cohorts at their defaults).
5. **`pcse_available()` already existed** in the landed wofost adapter (the bundle re-added
   it against a stale base); only the readiness endpoint and honesty docstrings were new.
6. **Delivered wiring bug fixed again:** the bundle's `routers/analysis.py` calls
   `main._current_ndvi_from_raster`, but its `main.py` never imported the new helper
   (AttributeError at request time). The landed `main.py` re-exports it.
