# raster-service unversioned-route migration plan (PR-R1)

Part of `API-VERSIONING-GUARD-IS-A-MIRROR-01`. This is the ownership-classification
deliverable for the `raster-service` slice, produced **after** the `generate_service_inventory.py`
classifier fix (Option B, PR #722) so the baseline below is measured on a corrected
inventory, not assumed from a stale one.

## Baseline (re-measured, not assumed)

`api_versioning_inventory.generated.json`, `service == "raster-service"`:

| classification | count |
|---|---|
| `versioned` | 48 |
| `legacy_unversioned_business` | 30 |
| `infra` | 3 |
| **total** | 81 |

The `legacy_unversioned_business` count is **still 30** — unchanged by Option B, because
none of raster-service's unversioned routes were misreported by the `APIRouter(prefix=...)`
composition bug (that bug only affected six sahool-platform files). This baseline is a
genuine independent measurement, not a carry-over assumption.

## Migration split (by ownership, not size)

The 30 routes split into four PRs. Route→PR assignment is pinned and falsification-tested
in `tests/architecture/test_raster_service_route_migration_plan.py` — a route landing in
the wrong bucket, or a new unversioned route appearing unclassified, fails that test.

### PR-R2 — internal and operational routes (8)

Job status/result and storage/upload/offline-pack management. All require
`x_agent_token` (`require_service_token`) — no browser exposure.

| method | path | file:line |
|---|---|---|
| GET | `/jobs/{job_id}` | `services/raster-service/routers/jobs.py:19` |
| GET | `/jobs/{job_id}/result` | `services/raster-service/routers/jobs.py:37` |
| POST | `/upload/raster` | `services/raster-service/routers/storage.py:26` |
| POST | `/upload/drone` | `services/raster-service/routers/storage.py:43` |
| GET | `/storage/stats` | `services/raster-service/routers/storage.py:65` |
| POST | `/storage/cleanup` | `services/raster-service/routers/storage.py:74` |
| GET | `/offline/packs` | `services/raster-service/routers/storage.py:87` |
| GET | `/offline/packs/{pack_name}` | `services/raster-service/routers/storage.py:115` |

**Real consumer requiring lock-step update:** `GET /jobs/{job_id}/result` is called by
`services/sahool-platform/api/raster_service_client.py:466` (`get_job_result`), itself
used by `imagery_automation.py:634` to read indicator-batch sub-job results. Migrating
this path to `/v1/jobs/{job_id}/result` **must** update `raster_service_client.py` in the
same PR, not defer it — this is not a classifier-only slice like sahool-platform's phase9-12
routers were in Option B.

### PR-R3 — imagery/catalog/process routes (20)

Analysis (8), async processing (3), internal STAC facade (3), observability (2),
timeseries (3), and one GIS boundary read (1). All `require_service_token` except the
three STAC routes and the bare `GET /imagery/timeseries`, which are `PUBLIC_CATALOG`
(bbox-scoped public search/catalog, no tenant data — see
`tests_v9/test_raster_endpoint_auth_coverage.py:PUBLIC_CATALOG`).

| method | path | file:line |
|---|---|---|
| POST | `/zones/classify` | `services/raster-service/routers/analysis.py:30` |
| POST | `/change/detect` | `services/raster-service/routers/analysis.py:48` |
| POST | `/fvc/compute` | `services/raster-service/routers/analysis.py:85` |
| POST | `/sar/rvi` | `services/raster-service/routers/analysis.py:111` |
| POST | `/terrain/slope` | `services/raster-service/routers/analysis.py:135` |
| GET | `/cog/validate` | `services/raster-service/routers/analysis.py:153` |
| POST | `/salinity/classify` | `services/raster-service/routers/analysis.py:168` |
| POST | `/salinity/calibrate` | `services/raster-service/routers/analysis.py:175` |
| POST | `/process` | `services/raster-service/routers/processing.py:28` |
| POST | `/raw/process` | `services/raster-service/routers/processing.py:59` |
| POST | `/process/batch` | `services/raster-service/routers/processing.py:78` |
| GET | `/stac` | `services/raster-service/routers/stac.py:17` |
| GET | `/stac/collections` | `services/raster-service/routers/stac.py:25` |
| POST | `/stac/mosaicjson` | `services/raster-service/routers/stac.py:33` |
| GET | `/info/{layer_id}` | `services/raster-service/routers/observability.py:213` |
| GET | `/indices` | `services/raster-service/routers/observability.py:253` |
| GET | `/imagery/timeseries` | `services/raster-service/routers/timeseries_routes.py:24` |
| POST | `/imagery/timeseries/analyze` | `services/raster-service/routers/timeseries_routes.py:77` |
| POST | `/imagery/timeseries/parallel` | `services/raster-service/routers/timeseries_routes.py:92` |
| GET | `/gis/admin-boundaries` | `services/raster-service/routers/fields.py:92` |

**Real consumers requiring lock-step update:**
- `GET /indices` — `raster_service_client.py:182` (`get_indices_sync`).
- `POST /process/batch` — `raster_service_client.py:448` (`process_indicator_batch`),
  driving `imagery_automation.py`'s indicator-collection flow.

Both must be updated in the same PR as their path migration.

`services/supervisor-agent/skills/remote_sensing_skill.py` (and its duplicate,
`services/supervisor-agent/remote_sensing_skill.py`) *describes* `/change/detect` and
`/fvc/compute` in text returned to an LLM caller (a capability description, not an HTTP
call — no `httpx`/`requests` invocation). Not a live consumer; update the description
text for accuracy but it is not a breaking-change risk.

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
