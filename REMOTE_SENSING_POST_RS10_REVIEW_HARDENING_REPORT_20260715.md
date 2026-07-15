# SAHOOL Remote Sensing — Post-RS10 Review and Hardening

Date: 2026-07-15

## Scope
Forensic review of the cumulative RS-1 through RS-10 implementation, focusing on concurrency, ownership boundaries, idempotency, service-to-service propagation, BFF failure semantics, and regression safety.

## Improvements applied

1. **Anomaly store concurrency hardening**
   - SQLite WAL enabled.
   - `synchronous=FULL` and `busy_timeout=10000` enabled.
   - anomaly creation changed to transactional `INSERT OR IGNORE` under `BEGIN IMMEDIATE`.
   - state transitions use `BEGIN IMMEDIATE`, version-constrained UPDATE, row-count verification, and explicit commit.
   - competing transitions now produce `aggregate_version_conflict`; no lost update.

2. **Service-to-service identity propagation**
   - vegetation baseline/timeline calls now forward both `Authorization` and `X-Tenant-Id`.

3. **RS-8 idempotency**
   - deterministic and distinct idempotency keys added for the vegetation snapshot and decision record writes.
   - returned bridge result exposes the keys for audit correlation.

4. **RS-10 idempotency**
   - outcome verification and learning attribution now forward the caller's idempotency key as an HTTP header, with deterministic fallback.

5. **Strict request contracts**
   - diagnosis, referral, follow-up, outcome verification, and attribution inputs reject unknown fields.

6. **Workspace BFF hardening**
   - `/readyz` added.
   - identifiers receive bounded non-empty validation without breaking legacy SAHOOL IDs.
   - unexpected upstream exception text is sanitized to `upstream_unavailable`; explicit HTTP failures remain `upstream_<status>`.

## Verification

- vegetation-analysis regression suite: 56 passed.
- new concurrency hardening tests: 2 passed.
- workspace BFF suite: 5 passed.
- indicators-service suite: 7 passed.
- RS-10 certification harness: 2 passed.
- Python compileall: passed.
- docker-compose YAML parse: passed.

## Important remaining production constraint

The current anomaly lifecycle store uses SQLite on a persistent volume. It is now safe against competing threads/processes sharing the same filesystem and database file, but it is **not a legal horizontally scaled multi-pod store**. Before scaling `vegetation-analysis-service` beyond one replica, migrate this store to PostgreSQL with tenant-scoped RLS and the same optimistic-concurrency invariant.

This report does not claim field, agronomic, controlled-intervention, or model-promotion certification.
