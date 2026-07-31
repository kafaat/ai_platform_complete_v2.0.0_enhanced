# raster-service unversioned-route migration plan (PR-R1)

Part of `API-VERSIONING-GUARD-IS-A-MIRROR-01`. This is the ownership-classification
deliverable for the `raster-service` slice, produced **after** the `generate_service_inventory.py`
classifier fix (Option B, PR #722) so the baseline below is measured on a corrected
inventory, not assumed from a stale one.

## Baseline (re-measured, not assumed)

`api_versioning_inventory.generated.json`, `service == "raster-service"`, **as measured
before PR-R2**:

| classification | count |
|---|---|
| `versioned` | 48 |
| `legacy_unversioned_business` | 30 |
| `infra` | 3 |
| **total** | 81 |

The `legacy_unversioned_business` count was **still 30** before PR-R2 — unchanged by
Option B, because none of raster-service's unversioned routes were misreported by the
`APIRouter(prefix=...)` composition bug (that bug only affected six sahool-platform
files). This baseline is a genuine independent measurement, not a carry-over assumption.

## Migration split (by ownership, not size)

The 30 routes split into four PRs. Route→PR assignment is pinned and falsification-tested
in `tests/architecture/test_raster_service_route_migration_plan.py` — a route landing in
the wrong bucket, or a new unversioned route appearing unclassified, fails that test.

### PR-R2 — internal and operational routes (8) — MIGRATED

Job status/result and storage/upload/offline-pack management. All require
`x_agent_token` (`require_service_token`) — no browser exposure. All 8 migrated to
`/v1/...` in this slice.

| method | old path | new path | file:line |
|---|---|---|---|
| GET | `/jobs/{job_id}` | `/v1/jobs/{job_id}` | `services/raster-service/routers/jobs.py:18` |
| GET | `/jobs/{job_id}/result` | `/v1/jobs/{job_id}/result` | `services/raster-service/routers/jobs.py:36` |
| POST | `/upload/raster` | `/v1/upload/raster` | `services/raster-service/routers/storage.py:25` |
| POST | `/upload/drone` | `/v1/upload/drone` | `services/raster-service/routers/storage.py:42` |
| GET | `/storage/stats` | `/v1/storage/stats` | `services/raster-service/routers/storage.py:64` |
| POST | `/storage/cleanup` | `/v1/storage/cleanup` | `services/raster-service/routers/storage.py:73` |
| GET | `/offline/packs` | `/v1/offline/packs` | `services/raster-service/routers/storage.py:86` |
| GET | `/offline/packs/{pack_name}` | `/v1/offline/packs/{pack_name}` | `services/raster-service/routers/storage.py:114` |

**Real consumer updated in lock-step:** `GET /jobs/{job_id}/result` was called by
`services/sahool-platform/api/raster_service_client.py:466` (`get_job_result`), itself
used by `imagery_automation.py:634` to read indicator-batch sub-job results. Updated to
`f"/v1/jobs/{job_id}/result"` in the same commit as the server-side path change — not
deferred — matching `services/sahool-platform/tests/test_p2_1_imagery_automation_raster_facade_guard.py`'s
facade-endpoint assertion, which was updated to match.

**Every other literal reference updated in the same PR** (repo-wide search, not
assumption): `tests_v9/test_raster_endpoint_auth_coverage.py`'s `SERVICE_ONLY` set,
`tests_v9/test_fields_put_and_mfa_api_contract_20260626.py`'s substring assertions,
`services/raster-service/test_stac_vrt.py`'s functional `TestClient` call (the one real
in-service functional test hitting `/jobs/{job_id}` directly), the `download_url` and
advisory `note` fields dynamically embedded in `/offline/packs` and `/process/batch`
responses (same "no stale embedded URL" discipline as the `tile_url_template` finding in
PR-R4's research), and `docs/openapi/API_MAP.md`. Two known-dead references were left
untouched deliberately: `tests_v9/test_mobile_backend_contract.py` (non-asserting —
`return`s a results list instead of `assert`ing, and scans a sibling directory that
doesn't exist in this repo — a pre-existing stale artifact, out of scope here) and
`tests_v9/test_roadmap_phase23.py`'s two soft checks (scan `services/raster-service/main.py`
for these paths, which were never there post-decomposition — already dead before this
PR, confirmed by grep). Dated historical reports (`FIX_ALL_REPORTED_ISSUES_20260626.md`,
`docs/history/PROVIDERS_GAPS_IMPLEMENTATION.md`) were left untouched, matching this
session's established precedent for point-in-time snapshots.

### PR-R3 — imagery/catalog/process routes (20) — MIGRATED

Analysis (8), async processing (3), internal STAC facade (3), observability (2),
timeseries (3), and one GIS boundary read (1). All `require_service_token` except the
three STAC routes and the bare `GET /imagery/timeseries`, which are `PUBLIC_CATALOG`
(bbox-scoped public search/catalog, no tenant data — see
`tests_v9/test_raster_endpoint_auth_coverage.py:PUBLIC_CATALOG`). All 20 migrated to
`/v1/...` in this slice.

| method | old path | new path | file:line |
|---|---|---|---|
| POST | `/zones/classify` | `/v1/zones/classify` | `services/raster-service/routers/analysis.py:29` |
| POST | `/change/detect` | `/v1/change/detect` | `services/raster-service/routers/analysis.py:47` |
| POST | `/fvc/compute` | `/v1/fvc/compute` | `services/raster-service/routers/analysis.py:84` |
| POST | `/sar/rvi` | `/v1/sar/rvi` | `services/raster-service/routers/analysis.py:110` |
| POST | `/terrain/slope` | `/v1/terrain/slope` | `services/raster-service/routers/analysis.py:134` |
| GET | `/cog/validate` | `/v1/cog/validate` | `services/raster-service/routers/analysis.py:152` |
| POST | `/salinity/classify` | `/v1/salinity/classify` | `services/raster-service/routers/analysis.py:167` |
| POST | `/salinity/calibrate` | `/v1/salinity/calibrate` | `services/raster-service/routers/analysis.py:174` |
| POST | `/process` | `/v1/process` | `services/raster-service/routers/processing.py:27` |
| POST | `/raw/process` | `/v1/raw/process` | `services/raster-service/routers/processing.py:58` |
| POST | `/process/batch` | `/v1/process/batch` | `services/raster-service/routers/processing.py:77` |
| GET | `/stac` | `/v1/stac` | `services/raster-service/routers/stac.py:16` |
| GET | `/stac/collections` | `/v1/stac/collections` | `services/raster-service/routers/stac.py:24` |
| POST | `/stac/mosaicjson` | `/v1/stac/mosaicjson` | `services/raster-service/routers/stac.py:32` |
| GET | `/info/{layer_id}` | `/v1/info/{layer_id}` | `services/raster-service/routers/observability.py:212` |
| GET | `/indices` | `/v1/indices` | `services/raster-service/routers/observability.py:252` |
| GET | `/imagery/timeseries` | `/v1/imagery/timeseries` | `services/raster-service/routers/timeseries_routes.py:23` |
| POST | `/imagery/timeseries/analyze` | `/v1/imagery/timeseries/analyze` | `services/raster-service/routers/timeseries_routes.py:76` |
| POST | `/imagery/timeseries/parallel` | `/v1/imagery/timeseries/parallel` | `services/raster-service/routers/timeseries_routes.py:91` |
| GET | `/gis/admin-boundaries` | `/v1/gis/admin-boundaries` | `services/raster-service/routers/fields.py:91` |

**Real consumers updated in lock-step:**
- `GET /indices` — `raster_service_client.py:191` (`get_indices_sync`), updated to `/v1/indices`.
- `POST /process/batch` — `raster_service_client.py:448` (`process_indicator_batch`),
  updated to `/v1/process/batch`, driving `imagery_automation.py`'s indicator-collection
  flow (its docstrings updated to match).

`services/supervisor-agent/skills/remote_sensing_skill.py` (and its duplicate,
`services/supervisor-agent/remote_sensing_skill.py`) *describes* `/change/detect` and
`/fvc/compute` in text returned to an LLM caller (a capability description, not an HTTP
call — no `httpx`/`requests` invocation). Not a live consumer; the description text was
updated to `/v1/change/detect`/`/v1/fvc/compute` for accuracy.

Two other embedded self-referential URLs were updated in the same PR (same "no stale
embedded URL" discipline as the `tile_url_template` finding from PR-R1's research):
`cloud_native_catalog.py`'s STAC landing-page `href` links (`self`/`search`/`data`, all
three now `/v1/stac...`), and the advisory `note` fields in `timeseries_routes.py` that
point callers at `/process` and `/imagery/timeseries/analyze`.

`scripts/ci/raw_data_processing_contract_guard.py` — a real CI-enforced contract guard,
not a test — asserts the literal `/raw/process` decorator string; updated to
`/v1/raw/process` in the same commit, verified locally (`raw_data_processing_contract_ok`).

Known-dead references left untouched after direct verification: `tests_v9/test_roadmap_phase23.py`'s
several soft checks that scan `services/raster-service/main.py` for these paths
(confirmed absent from `main.py` both before and after this PR — post
router-decomposition, these routes live in `routers/`, not `main.py`) and two mock-URL
substring checks (`"/process" in url`) that remain trivially true regardless of the
`/v1/` prefix. `sahool-platform/api/routers/gis_cloud_native.py`'s own `/stac`/`/stac/collections`
decorators are a different service's routes with the same bare text before their own
router-prefix composition — coincidental, unrelated, untouched.

### PR-R4 — tile and rendering routes (2)

| method | path | file:line |
|---|---|---|
| GET | `/tiles/{layer_id}/{z}/{x}/{y}.png` | `services/raster-service/routers/tiles.py:23` |
| GET | `/layers/{layer_id}/tilejson` | `services/raster-service/routers/tiles.py:37` |

These are `layer_scoped` (`require_layer_tenant` + `require_layer_tenant_authorized`),
architecturally distinct from the **already-versioned** `/v1/fields/{field_id}/tiles/...`
family served by `routers/fields.py` — that family is the one the frontend actually calls
(`frontend/src/services/api.ts:3150` via `rasterBaseUrl()`), not these bare `layer_id`
routes.

**Consumer search performed before migrating (per explicit caution: nginx/proxy, frontend
tile URLs, tenant propagation, cache keys, signed/query auth, compat aliases):**

- **nginx**: `/api/raster/` (`nginx/nginx.v9.conf:252`, `nginx/nginx.fixed.conf:65`,
  `frontend/nginx.conf:75`) is a transparent prefix-stripping proxy — it does not
  hardcode individual raster-service paths, so it requires **no config change** for any
  path migration under it, tile routes included.
- **frontend/mobile**: no literal reference to `/tiles/{layer_id}` or
  `/layers/{layer_id}/tilejson` anywhere in `frontend/src/` or
  `mobile/sahool_app/lib/` (searched directly, not just grep-for-tiles — confirmed the
  frontend's own tile calls target the separate `/v1/fields/{field_id}/tiles/...` family).
- **dynamic URL construction**: `raster_job_orchestration.py:230` embeds
  `"tile_url_template": f"/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png"` in `/process` job
  results. Traced every reader of `get_job_result()` — `imagery_automation.py`'s
  `_fetch_index_mean` reads only `stats.mean`/`stats.valid_pixels`. **No code anywhere
  reads the `tile_url_template` field** — it is dead data, not a live integration. Update
  it in the same PR for internal consistency (stop emitting a URL that would 404 with a
  stale prefix), but it does not gate the migration on a hidden consumer.

**Conclusion:** despite the general caution tile routes deserve, this specific pair has
**no live external caller** (browser, mobile, or cross-service) as of this baseline. PR-R4
can migrate the path directly; it does not need a compatibility-alias period the way a
route with a confirmed live caller would.

### PR-R5 — compatibility aliases + removal proof

Not a route bucket — a follow-up verification PR after R2-R4 land. Confirms (a) every
real consumer identified above (`raster_service_client.py`'s three call sites) was updated
in lock-step, not left on a stale bare path; (b) no bare-path alias is needed for R2-R4
specifically, since none of the 30 routes have a browser-facing or mobile-facing live
caller (all real consumers found are internal service-to-service, updatable in the same
commit as the server-side path change); (c) `api_versioning_legacy_allowlist.generated.json`
ceiling drops by exactly 30 once R2-R4 are merged, with no phantom cross-service duplicate
introduced (repeat the `build_platform_catalog.py --generate` duplicate-group check done
in Option B, since this migration touches 21 bare texts that could collide with another
service's routes of the same bare text — check each before merging, don't assume).

## Auth-classification cross-reference

The security taxonomy (`service_only` / `layer_scoped` / `public_catalog`) already exists
as enforced code in `tests_v9/test_raster_endpoint_auth_coverage.py` and is orthogonal to
this migration-bucket split — cross-referenced here, not duplicated:

- PR-R2's 8 routes: all `service_only`.
- PR-R3's 20 routes: `service_only` except `/stac`, `/stac/collections`, `/stac/mosaicjson`,
  `/imagery/timeseries` (bare GET) which are `public_catalog`.
- PR-R4's 2 routes: `layer_scoped`.

## Sequencing

`raster-service` → `soil-service` → `mcp_servers` → `erp-bridge` (`odoo-bridge` is
erp-bridge's historical alias, not an independent service). `Auth` stays deferred until
live consumers are proven. Recorded in `sahool-brain/decisions/ledger.md`.
