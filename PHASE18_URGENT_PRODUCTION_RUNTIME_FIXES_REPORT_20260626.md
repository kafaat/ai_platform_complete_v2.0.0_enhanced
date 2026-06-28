# Phase 18 — Urgent Production Runtime Fixes

## Scope

This patch addresses the production gaps found during direct source review of the Phase 17 archive.

## Fixes Applied

1. **GitHub Actions shell syntax fixed**
   - Repaired the malformed `supply-chain-static-scan` shell block in `.github/workflows/sahool-production-gates.yml`.
   - Extended `scripts/ci/validate_ci_gates.py` to extract and run `bash -n` against literal `run: |` workflow blocks, so this class of defect is caught by CI validation.

2. **Chaos/E2E failures are blocking**
   - Removed `|| true` from the E2E and outbox checks in `scripts/chaos/run_chaos_tests.sh`.
   - Added a recovery smoke step at the end of the chaos harness.

3. **Production persistence is fail-closed**
   - `services/sahool-platform/api/phase_runtime_store.py` now raises explicit FastAPI errors in production/staging or when `PHASE_RUNTIME_PERSISTENCE_REQUIRED=true` if `db_pool` or `X-Tenant-Id` is missing for Phase 9-12 writes.
   - Contract-test fallback behavior remains available for non-production local tests.

4. **RLS tenant context tightened**
   - Tenant-scoped persistence now validates tenant availability in production mode.
   - Additional persistence paths set `app.tenant_id` before RLS-protected writes.

5. **Runtime workers added**
   - Added `services/sahool-platform/api/phase_runtime_workers.py`.
   - Added compose services for:
     - `sahool-phase-runtime-outbox-worker`
     - `sahool-plugin-runtime-worker`
     - `sahool-model-registry-worker`
     - `sahool-actuator-dispatch-worker`
   - Workers use `JOBS_DATABASE_URL` and fail closed when external side-effect dependencies are missing.

6. **RLS-safe job policies**
   - Added `migrations/v113_phase_runtime_workers_jobs.sql` so `sahool_jobs` can process queue tables without using database bypass privileges.

7. **Manifest confusion removed**
   - `migrations/MANIFEST.md` now mirrors the canonical `migrations/MANIFEST.txt` instead of containing a stale partial list.

## Remaining Runtime Requirements

The workers are wired and safe, but real side effects still require production configuration:

- `NATS_URL` and NATS client availability for outbox publication.
- Plugin execution backend if plugins should run beyond plan/output validation.
- Model serving backend if rollback should update a live serving plane.
- Verified MQTT/Modbus/LoRaWAN/pivot/pump adapters before enabling physical actuation.

## Validation

- CI gate validation catches workflow shell syntax.
- Chaos harness no longer hides E2E/outbox failures.
- Production validation requires v113 migration.
- Release packaging tracks the new worker and migration assets.
