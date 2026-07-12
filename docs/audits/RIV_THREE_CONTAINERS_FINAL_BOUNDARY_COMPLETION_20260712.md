# RIV Three-Container Boundary Completion — 2026-07-12

## Base

Applied to `sahool_70bc054_riv_runtime_timeline_verified.zip` (reported tree tip `c61c0c8`).
This delta intentionally does **not** introduce registry-v2 or the deferred
`geospatial_contract_index_guard`.

## Implemented

### Raster service

- Added `GET /v1/fields/{field_id}/indicator-observation-bundle`.
- Requires internal service token and tenant-scoped field authorization.
- Deduplicates requested indicator names while preserving first-seen order.
- Returns only real COG-backed products; unavailable products are explicit.
- Publishes scene IDs and acquisition dates for every returned observation.
- Computes `bundle_consistency` and `mixed_scene`; no synthetic fallback.

### Vegetation analysis

- Replaced seven independent `indicator-grid` calls with one observation-bundle call.
- Propagates `X-Tenant-Id` and `X-Agent-Token` to Raster.
- Fails closed on absent service token, unavailable bundle, or mixed-scene bundle.
- Removed Sentinel Hub/CDSE credentials and direct provider/token code from runtime.
- Startup contract now reports Raster consumer readiness and direct-provider access disabled.
- Service version advanced from 9.1.0 to 9.2.0.

### Compose trust boundary

For Vegetation in `docker-compose.v9.yml` and `docker-compose.fixed.yml`:

- Removed SH/CDSE/Copernicus provider credentials and provider URLs.
- Added explicit `RASTER_SERVICE_URL`.
- Added required `SAHOOL_AGENT_TOKEN` for authenticated internal consumption.

Provider credentials remain owned by Raster.

## Added regression tests

- Raster bundle single-scene consistency.
- Raster bundle mixed-scene detection.
- Vegetation tenant and service-token propagation.
- Vegetation mixed-scene rejection.
- Static proof that Vegetation runtime contains no provider credentials or direct-provider functions.

## Verification

- Raster: `246 passed, 1 skipped`.
  - Skip: PostgreSQL integration test; no integration DB URL in this environment.
- Vegetation: `41 passed`.
- Indicators: `5 passed`.
- `riv_boundary_gate`: pass.
- `raster_production_truth_guard`: pass.
- `intelligence_governance_gate`: pass.
- `indicators_registry_gate`: pass.
- `generate_indicator_artifacts.py --check`: pass.
- Python compile: pass.
- Compose YAML parse: pass.

## Deliberately deferred

- Registry-v2 semantic renaming (`savi/msavi`, `ndmi/moisture`).
- `geospatial_contract_index_guard`, which is not present in this base tree.
- Live PostgreSQL/CDSE/MinIO container certification.

---

## Integration note — runtime-truth completion (landed shape, 20260712)

The follow-up bundle `sahool_riv_three_containers_runtime_truth_completed_20260712.zip`
was integrated **on the landed shape**: only the true delta was taken, and the delivered
artifacts' latent bugs (their gate/test proofs had never run — always SKIPPED) were fixed.

### Genuine delta adopted (production truth for field source)
- `vegetation_runtime.py`: the synthetic `FIELD_REGISTRY` is now **empty**; `load_field`
  reads the tenant-scoped platform catalog behind `FEATURE_SENTINEL_DB_FIELDS`
  (auto-enabled when `PLATFORM_API_URL` is set) and **never fabricates** — the legacy
  branch dead-ends to `None` with `legacy_field_registry_forbidden`. `ALLOW_LEGACY_FIELD_REGISTRY`
  defaults OFF in every environment.
- New `list_fields_from_platform(tenant_id)` — tenant-scoped, service-token authenticated,
  no local enumeration fallback (503 when unconfigured/unreachable).
- `routers/analysis.py` all-fields NDVI now iterates the platform catalog instead of the
  synthetic registry (replaces the prior honest `501` stub).
- Compose (`v9` + `fixed`): `PLATFORM_API_URL: http://sahool-platform:8000` wired into the
  vegetation service so the field source resolves at runtime.
- New `test_platform_field_catalog_boundary.py` asserts tenant-scoping + auth + empty registry.

### Delivered bugs fixed (bundle gates/tests were stale against the bundle's own runtime)
1. `scripts/ci/p1_main_decomposition_guard.py` — the delivered guard still required
   `fetch_from_cdse` in the vegetation runtime, but the runtime no longer contains it
   (RIV removed direct provider fetch). The guard failed against its own tree. Fixed:
   `fetch_from_cdse` moved from the required `veg_heavy` set to the `banned` set alongside
   `fetch_from_sentinel_hub` — both direct-provider fetches must be **absent**.
2. `scripts/ci/consumer_contract_gate.py` — the delivered gate's WS-A check targeted
   `_real_index_mean_from_raster`, which the observation-bundle refactor deleted. Fixed:
   the check now targets `run_analysis` consuming `_real_observation_bundle_from_raster`
   and still unwrapping the ValidatedIndicatorProduct envelope (`indicator_product`,
   `quality_score`, `provenance`).
3. `tests_v9/test_vegetation_raster_ndvi.py` — the delivered test still asserted the old
   7-request per-index contract (`asyncio.gather`, `_real_index_mean_from_raster`). Rewritten
   to the single observation-bundle contract; behavioral tests inject the field fixture via
   function-scoped `monkeypatch` (no synthetic registry to fall back on).
4. `tests_v9/test_sentinel_field_source.py` — 4 tests asserted the now-dead synthetic-registry
   fallback. Reconciled to the production-truth contract (load_field never fabricates → `None`).
5. `scripts/ci/vegetation_agriai_full_closure_gate.py` — its needle asserted the old
   production-only legacy default. Updated to the stronger contract (empty `FIELD_REGISTRY`,
   legacy default OFF in every environment, `legacy_field_registry_forbidden`).
6. `vegetation_runtime.py` carried an unused `import asyncio` (leftover from the removed
   `asyncio.gather` per-index fetch) — removed (ruff F401).

### Verification on the landed shape
- `pytest -m unit`: **2913 passed, 5 skipped**.
- Vegetation service tests: **43 passed**; three-container + platform-catalog boundary tests pass.
- Gates: `p1_main_decomposition_guard`, `consumer_contract_gate`, `riv_boundary_gate`,
  `vegetation_agriai_production_gate` / `_completion_gate` / `_full_closure_gate`,
  `vegetation_container_contract_guard`, `compose_env_contract_gate` — all pass.
- `runtime_real_smoke.sh`: `runtime_real_smoke_ok` (173 passed).
- `build_release_bundle` + `validate_release_package`: 4133 checksums verified.
- `ruff check` / `ruff format --check`: clean.
