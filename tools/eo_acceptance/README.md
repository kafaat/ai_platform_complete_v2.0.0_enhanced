# Earth observation acceptance experiments

These runners create reviewable JSON evidence. `PASS` means the tested correctness
contract passed, not production readiness or a measured 20% improvement. Adoption
requires correctness **and** the separately reported performance condition.

Install from the repository root:

```sh
python -m pip install -r tools/eo_acceptance/requirements.txt
python -m pytest -q tools/eo_acceptance/tests --confcutdir=tools/eo_acceptance
```

## 1. CDSE STAC catalogue equivalence

```sh
python -m tools.eo_acceptance.run stac \
  --manifest tools/eo_acceptance/stac-manifest.json \
  --repeats 20 --output /tmp/eo-stac.json
```

For a complete correctness comparison before spending quota on 20 repeats, add
`--correctness-only`. This performs one paired crawl per query, leaves P50/P95 and
the adoption verdict unset, and explicitly marks performance as unmeasured.
Reports checkpoint completed crawls atomically; an HTTP failure retains partial
sample metrics and a numeric upstream status without exposing request URLs or
credentials. Partial samples are not automatically reused as a new benchmark.

The fixed 24-month windows and example AOIs represent Al Hazm and Tihama, not
verified farm boundaries. Check collection names and sort support on both APIs.
Unsupported requests fail; the runner never silently drops filters or ordering.
Set `CDSE_STAC_TOKEN` through the environment when authenticated. One process-wide
limiter accounts for both APIs and retries (10/s, 60/min anonymous or 240/min
authenticated). Run a single instance per shared IP/token; it does not coordinate
multiple machines. No cache/fallback client is used. Complete GET/POST pagination,
next-body replacement/merge, duplicate IDs, loops and cross-origin links are tested.

Reports compare `(collection,id)`, capture dates and asset declarations. Different
asset URLs are allowed because hosts may change; pixel accessibility is explicitly
`NOT_MEASURED`. Review metadata differences and paired acquisition timing before
attributing changes to a provider. Do not switch production from this report alone.

## 2. VRT windows and NDVI

Provide a JSON manifest with `scenes` (each containing `id` and `paths` with `red`,
`nir`, `scl`) and `fields` (each containing `id` and WGS84 Polygon `geometry`). Paths
may reference local rasters or approved readable assets. Example structure:

```json
{"scenes":[{"id":"declared-scene","paths":{"red":"/data/B04.tif","nir":"/data/B08.tif","scl":"/data/SCL.tif"}}],"fields":[{"id":"example-only","geometry":{"type":"Polygon","coordinates":[[[44.75,16.05],[44.751,16.05],[44.751,16.051],[44.75,16.051],[44.75,16.05]]]}}]}
```

```sh
python -m tools.eo_acceptance.run raster --manifest /data/eo-raster.json \
  --repeats 20 --output /tmp/eo-raster.json
```

The correctness oracle aligns source pixels independently with `reproject` and
compares them with production `stac_vrt.build_band_vrt` and `band_math` (maximum
NDVI error 1e-5, identical validity masks, at least one valid pixel). Sources must
declare their calibration in TIFF metadata. No DN calibration is guessed. The
oracle reads complete source bands: budget RAM for it on full Sentinel tiles.
This tests helper behavior, not the full C1 admission or HTTP/persistence pipeline.
SCL uses nearest-neighbour alignment. The declared comparison policy excludes SCL
3/8/9/10/11, nonfinite spectral data, zero denominators and reflectance outside
[-0.05,1.2]. Aggregation-order differences are a separate diagnostic.

The performance trial compares repeated per-field VRT construction with one shared
scene VRT; both compute field windows. It alternates strategy order, records the
first open separately, then measures at least 20 samples. It records P50/P95,
process peak RSS and materialized array bytes. These bytes are **not network bytes**.
OS/provider caches are uncontrolled; neither strategy is labelled genuinely cold.
The union AOI has a 1,000,000-pixel budget. Run separated groups for distant fields.
The report explicitly identifies whether the requested 12-scene/100-field matrix
was supplied. Local regression fixtures are synthetic, not Yemen observations.

## 3. PostGIS subdivision

```sh
export EO_TEST_DATABASE_URL='postgresql://.../isolated_test_database'
python -m tools.eo_acceptance.run spatial --output /tmp/eo-spatial.json
```

PostGIS must already exist. The runner creates 100 synthetic geometries and their
subdivisions in temporary tables, adds GiST indexes, and compares `ST_Intersects`
with tenant predicates and deduplicated field IDs, including empty/boundary cases.
It records version, `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`, P50/P95 and total
relation sizes. Everything runs under forced transaction rollback. Warm-cache
synthetic results do not prove production query speed, update cost or an advantage
of PostGIS 3.7rc3. No database upgrade or extension installation is performed.

The CI workflow provisions disposable PostGIS 16/3.4 and retains test/measurement
artifacts. A missing local DSN is an explicit skip, never counted as a passed SQL
experiment. Live STAC is intentionally operator-run to avoid credentials and quota
use on every pull request.
