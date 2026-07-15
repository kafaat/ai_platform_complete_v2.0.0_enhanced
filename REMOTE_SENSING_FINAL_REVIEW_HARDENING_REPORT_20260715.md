# SAHOOL Remote Sensing — Final Review and Hardening

Date: 2026-07-15

## Scope
Final forensic review of the cumulative RS-1 through RS-10 implementation after the post-RS10 hardening pass. The review focused on tenant isolation, optimistic concurrency, router registration integrity, timezone correctness, strict BFF input boundaries, Docker/source parity, and regression safety.

## Improvements applied

1. **Tenant-scoped anomaly storage operations**
   - `AnomalyStore.get()` can now enforce `tenant_id` in SQL.
   - `AnomalyStore.transition()` reads and updates using the tenant scope inside the transaction.
   - Diagnosis, decision-referral, transition, and verification routes use tenant-scoped store calls.
   - Cross-tenant references return not-found semantics without exposing aggregate existence.

2. **Timezone-safe ground-verification callbacks**
   - `VerificationCompletion.completed_at` now rejects timezone-naive timestamps.
   - Valid timestamps are normalized to UTC when persisted in the anomaly payload.

3. **Router import-cycle removal**
   - Strict anomaly request contracts moved to `anomaly_requests.py`.
   - The process-local anomaly store wiring moved to `anomaly_runtime.py`.
   - Diagnosis routes no longer import state from another router module.
   - Tests and schema tools can import request contracts without triggering `main` or router registration.

4. **Source-tree and production-image parity**
   - `main.py` resolves the repository-level `shared` package when executed from the source tree.
   - Dockerfile copies the new request/runtime modules.
   - Automatic router registration now includes RS anomaly and diagnosis routes consistently in full-suite execution.

5. **Workspace BFF boundary tightening**
   - Empty or excessively large Authorization values are rejected.
   - `tenant_id`, `field_id`, and `season_id` must be bounded non-empty values.
   - Existing upstream error sanitization and partial-result semantics remain intact.

6. **Regression guards**
   - Added a tenant-isolation test proving a foreign tenant cannot read or transition an anomaly.
   - Added a validation test proving naive callback timestamps are rejected.
   - Full router decomposition guard now passes in the complete service suite, not only in isolation.

## Verification

- vegetation-analysis-service full suite: **60 passed**
- remote-sensing-workspace-bff suite: **5 passed**
- indicators-service boundary/timeline suite: **6 passed**
- RS-10 technical certification harness: **2 passed**
- Total targeted verification: **73 passed, 0 failed**
- Python compileall: passed
- docker-compose YAML parse and BFF service presence: passed

## Production constraints that remain explicit

1. The anomaly aggregate store remains SQLite-backed and therefore legal only for a single vegetation-analysis replica. Horizontal scaling still requires PostgreSQL, tenant-scoped RLS, and the same version-constrained update invariant.
2. Authoritative decision/outcome execution still requires the live decision-service database, migrations, and service-to-service identity configuration.
3. Ground verification still requires a live task owner and callback credentials.
4. Technical code readiness is not agronomic, controlled-intervention, or model-promotion certification.

## Final assessment

The RS-1 through RS-10 code path is now internally coherent for the implemented single-replica deployment profile. The final pass removed a real cross-tenant TOCTOU weakness and a router-registration import cycle that could silently omit RS routes during source-tree execution. No claim is made that live-field or seasonal certification has been completed.
