# SAHOOL Test Repair Report — 2026-06-26

## Scope
Uploaded archive: `signal-2026-06-26-173924_fields_503_create_fixed(1).zip`

Focus areas requested: migrations, persistence/save contract, pipeline/field imagery and indices container, tenant isolation, endpoint auth coverage.

## Failures found and fixed

1. **Missing `nats.aio` dependency during mobile push tests**
   - Failure: `ModuleNotFoundError: No module named 'nats.aio'` in `tests_v9/test_c4m1_mobile_push.py`.
   - Fix: added `nats-py>=2.3.0` to `tests_v9/requirements-test.txt`.

2. **Unauthenticated lab/field sampling endpoints**
   - Failure: endpoint auth guard found four unauthenticated endpoints in `api/routers/soil_sampling.py`:
     - `/api/v1/fields/{field_id}/lab-context`
     - `/api/v1/lab/samples` GET
     - `/api/v1/lab/samples` POST
     - `/api/v1/lab/soil-results` POST
     - `/api/v1/lab/water-results` POST
   - Fix: added `require_permission` dependencies:
     - read endpoints: `Permission.FIELD_VIEW`
     - write/result endpoints: `Permission.FIELD_EDIT`

3. **Migration manifest drift**
   - Failure: `v_ai_recommendation_runtime.sql` existed on disk but was missing from `migrations/MANIFEST.txt`.
   - Fix: added it to `MANIFEST.txt`.

4. **RLS missing for AI recommendation runtime tables**
   - Failure: `recommendation_reviews` and `recommendation_feedback` have `tenant_id` but no detected RLS.
   - Fix: added explicit RLS/FORCE protection in `v_ai_recommendation_runtime.sql` using `_sahool_apply_tenant_rls`, with fallback explicit policies.

5. **RLS missing for `field_state` created after propagate**
   - Failure: `tools/sahool_inspector.py` flagged `field_state` in `v104_fields_create_contract.sql` as created after RLS propagation without explicit RLS/FORCE.
   - Fix: added explicit RLS/FORCE protection for `field_state` in `v104_fields_create_contract.sql`.

6. **Global SIGTERM handler pollution during tests**
   - Failure: importing `services/mcp_servers/wofost_server.py` registered a process-wide SIGTERM handler, interfering with `subprocess.run(..., timeout=...)` in mutation tests.
   - Fix: moved SIGTERM handler registration under `if __name__ == "__main__"`.

7. **Missing `JWT_SECRET` in MCP integration test environment**
   - Failure: `tests_v9/test_mcp_servers.py::test_unauthorized_invalid_scope` accessed `os.environ["JWT_SECRET"]` directly.
   - Fix: set default `JWT_SECRET` in `tests_v9/conftest.py` from `TEST_JWT_SECRET`.

## Verification executed

Full `tests_v9` suite was executed in chunks to avoid long single-process timeout/output limits.

- `tests_v9` collection: **2263 tests**
- Chunk 0–65: **453 passed, 18 skipped**
- Chunk 66–130: **474 passed, 20 skipped**
- Chunk 131–146: **96 passed, 18 skipped**
- Chunk 147–160: **98 passed**
- Chunk 161–195: **283 passed, 18 skipped**
- Chunk 196–205: **235 passed**
- Chunk 206–230: **290 passed, 23 skipped**
- Chunk 231–end: **221 passed, 16 skipped**

Total executed outcome by chunks: **2150 passed, 113 skipped, 0 failed**.

## Targeted requested area verification

The following focused suite passed:

- migrations
- field geometry contract
- field merge/split atomic behavior
- field intelligence endpoints
- NDVI enrichment
- GIS GeoJSON kernel
- raster endpoint auth coverage
- raster tenant authorization
- raster job store
- raster reflectance scaling
- Sentinel field source
- vegetation and raster NDVI

Result: **142 passed, 4 skipped, 0 failed**.

## Notes

Skipped tests are integration/live-service tests requiring external running services such as Postgres/PostGIS, MCP services, video streaming services, or full E2E environment. They were not counted as failures.
