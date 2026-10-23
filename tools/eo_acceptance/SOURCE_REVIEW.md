# Source and code review — 23 October 2026

Reviewed repository baseline: `d23b320ae6c437273a8c8a6a1ba9fc5f111b1e1c`.

| Claim | Verification and limitation |
| --- | --- |
| New CDSE SFEOS endpoint, 16 October | Confirmed in the primary announcement: `https://stac.opensearch.dataspace.copernicus.eu/v1`, burst 10/s, anonymous 60/min, authenticated 240/min. No numerical latency benchmark is published. |
| Old endpoint sunset | The announcement still says 12 January 2026 despite its October publication. Treat as unresolved; do not assume 2027. |
| PostGIS 3.7.0rc3, 21 October | Confirmed. Release notes list prepared-distance/caching for ST_DWithin, matching overview reuse in raster2pgsql and missing-NoData preservation in ST_MapAlgebra. These are cumulative release notes, not proof all changes landed this week or accelerate NDVI. |
| NDVI downscaling paper | Publisher abstract/full-text search extracts confirm 2.03 dB synthetic gain, 0.62 dB calibrated cross-sensor gain, 272 held-out pairs, order RMSE 0.01054 and 12.49% above 0.01; about 30.6x parameter count and unmeasured inference speed. Version notes confirm 18 October availability. Direct full-page retrieval returned HTTP 429; full-text figures were verified against publisher search extracts, not an independently downloaded PDF. |
| GDAL | Primary download page lists 3.13.3, 18 August. Processed VRT docs confirm Expression and automatic input unscale since 3.11. This does not establish the behavior of every VRT class. |
| ST_Subdivide | Official docs describe possible gains from smaller bounding boxes and cheaper rechecks. No guaranteed gain for SAHOOL. |

Primary sources:

- https://dataspace.copernicus.eu/news/2026-10-16-new-sfeos-stac-catalogue-endpoint
- https://www.postgis.net/2026/10/PostGIS-3.7.0rc3/
- https://www.mdpi.com/1424-8220/26/20/6601
- https://www.mdpi.com/1424-8220/26/20/6601/notes
- https://gdal.org/en/stable/download.html
- https://gdal.org/en/stable/drivers/raster/vrt_processed_dataset.html
- https://postgis.net/docs/ST_Subdivide.html

## Code findings

- `services/raster-service/cdse_client.py::search_scenes` uses Sentinel Hub
  `/api/v1/catalog/1.0.0/search`, excludes assets in its projection and deliberately
  omits provider-rejected `sortby`. The public old/new CDSE STAC comparison is a
  separate experiment; replacing that URL in the production client is not justified.
- `stac_search.py` dispatches historical Sentinel discovery through the configured
  CDSE gate. `stac_client.py` has cache/fallback behavior, unsuitable for uncached
  provider-comparison timings.
- `stac_vrt.py` builds an ordinary VRT, uses nearest-neighbour WarpedVRT sidecars
  and preserves scale/offset as metadata. It does not use `VRTProcessedDataset`.
  `band_math.to_reflectance` applies explicit coefficients. Therefore automatic
  unscale in the newer VRT class is a migration concern, not an established
  double-scaling defect in the inspected code.
- `stac_c1_processing.py` requires exact C1 scene/assets, asset/TIFF calibration
  agreement, a polygon and a pixel budget. Legacy Element84 containment remains
  in place; the new tests do not bypass or certify this admission policy.
- `raster_pixel_processing.py` already clips before reading and caches converted
  bands for the exact open dataset/clip context. A claim that all current reads
  load the whole tile would be wrong. Shared scene-VRT measurements are a named
  helper experiment, not evidence that production lacks existing batch reuse.
- Inspected platform field/drawing/yield paths use ST_Intersects. The administrative
  boundary query uses the `&&` bbox operator, despite a comment referring to
  ST_Intersects. Do not replace bbox-only semantics with an exact predicate and
  call it equivalent. No ST_DWithin speedup is inferred for these paths.

## Execution evidence and remaining live inputs

Local tests cover real temporary TIFF/VRT reads, mixed SCL resolution, NoData,
cloud/shadow values, offsets 0 and -0.1, independent NDVI and strategy timing;
STAC transport behavior is tested with controlled HTTP responses. Live CDSE and
the production 12-scene/100-field matrix remain unproven. Local PostGIS is absent;
its integration test explicitly skips and the added CI job supplies a disposable
database. No production provider, database version or agricultural policy changed.

CI execution on `14ea5a78f20703706895d444013c2236fdd81950` subsequently
passed all **16/16 tests**, including real temporary PostGIS queries, and completed
the standalone spatial runner. Evidence is retained in
[run 39928216767](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/actions/runs/39928216767):
`eo-acceptance-evidence` (artifact 12489852966) and `eo-spatial-measurements`
(artifact 12490536175). This validates the synthetic integration, not production
speed or the real-scene matrix. Workflow-only follow-up adds required version
comments and pins the actually pulled image digest.
