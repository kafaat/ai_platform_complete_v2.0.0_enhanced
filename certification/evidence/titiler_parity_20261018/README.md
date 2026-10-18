# TiTiler parity: legacy `sahool-titiler` 0.18.6 vs `raster-tiler-service` 0.22.4 (2026-10-18)

**Question:** can the legacy tiler (compose profile `legacy-tiler`) be retired without breaking what SAHOOL sends it?
**Answer measured here:** for SAHOOL's only code caller the successful comparable tiles agree; the float viridis case differs (500 vs flat-colour 200). Retiring it is
**not** yet safe, for the reasons under *What this means*. Nothing was deployed, and Railway was not touched.

## Method

- **No images.** The proxy blocks the GHCR blob host (`docker pull` → 403), so both versions ran from PyPI in separate
  Python 3.12 venvs:
  - **Legacy:** `titiler.application==0.18.6` with resolver-chosen dependencies.
  - **Wrapper:** `services/raster-tiler-service/requirements.txt` (pinned), served through the real `main.py`.
  - Versions are in [`environment_and_audit.json`](environment_and_audit.json). GDAL is 3.12.x from the rasterio wheels
    in both, **not** the GDAL inside either image.
- **Request matrix:** [`scripts/diagnostics/titiler_parity.py`](../../../scripts/diagnostics/titiler_parity.py).
  - Derived from `shared/gis/cog_tile_proxy.py:76`, SAHOOL's only TiTiler caller:
    `GET /cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=…[&colormap_name=…][&rescale=a,b]`.
  - Plus the compose `/healthz` checks, and `info`/`statistics` as operator diagnostics.
  - `tests_v9/test_titiler_parity_harness.py` turns red if the caller's path or parameters drift away from the matrix.
    A manual mutation of each turned it red.
- **Reference COGs:** two deterministic COGs from [`make_reference_cogs.py`](make_reference_cogs.py) (rio-cogeo,
  `cog_validate` true; sha256 in the environment file). Both are read as local paths by both services.
  - Float32 NDVI-like, EPSG:4326, NaN corner.
  - uint8 RGB, EPSG:32638, nodata border.

## Results

| Case (caller) | Float32 NDVI | uint8 RGB |
|---|---|---|
| `tile` (sahool-platform `gis_cloud_native`, no colormap) | identical | identical |
| `tile_viridis` (raster-service `routers/tiles.py` default, no rescale) | **legacy 500, wrapper 200** | 500 on both ("Source data must be 1 band") |
| `tile_viridis_rescale` (same, with rescale) | identical | 500 on both |
| `tile_colormap_mixed_case` (`RdYlGn`; the caller regex admits it) | 422 on both | 422 on both |
| `tile_outside_bounds` | 404 on both | 404 on both |
| `healthz` (compose, status only) | 200 on both; **bodies differ** | same |
| `info` (diagnostic) | differs: `minzoom`/`maxzoom` only in legacy, `crs` only in wrapper | differs as left, and **`bounds` are lon/lat in legacy but native UTM metres in the wrapper** |
| `statistics` (diagnostic) | identical | identical |
| `tile_without_tms` (`/cog/tiles/{z}/{x}/{y}.png`, no SAHOOL caller) | **legacy 200, wrapper 404** | same |

`tile_viridis` on the float COG needs a closer look. The wrapper's 200 is **one flat colour** over all 65,536 opaque
pixels: the float values are not rescaled. With `rescale=-1,1` the same request gives 76 colours, identical on both.

## What this means

1. **Comparable successful tile responses are pixel-identical.** The float `tile_viridis` case is an exception to status parity: legacy 500 vs wrapper 200 with one flat colour. This prevents a blanket compatibility claim.
   This wording was reconciled during consolidation; raw measurements remain unchanged.
2. **A float raster without `rescale` shows no data on either service, and the wrapper hides it.** The case is the
   default `viridis` with no `rescale`:
   - Legacy fails with 500, and `cog_tile_proxy` reports 502.
   - The wrapper returns one flat colour, and the proxy passes it through as success.

   The wrapper is already the default `TITILER_URL` target (`docker-compose.v9.yml:869`, `:1516`). So wherever that
   default holds, this silent case exists today, independent of retirement. Whether production layers reach this path
   with float COGs and no `rescale` was not measured. New gap `FLOAT-COG-TILE-WITHOUT-RESCALE-RENDERS-FLAT-01`.
3. **The wrapper as deployed cannot do the diagnostics legacy is kept for.** Its compose service
   (`docker-compose.v9.yml:11-40`) has neither the `raster-data` volume nor any `AWS_*`/S3 variable. Two guards require
   both on `sahool-titiler`:
   - `scripts/ci/minio_s3_contract_gate.py:303-310`
   - `scripts/ci/compose_env_contract_gate.py:155`

   Local-file reads match at code level here. MinIO/S3 reads were **not** measured.
4. **External clients break:** the TMS-less tile path and `info` bounds change. No SAHOOL code calls either, but an
   operator script or bookmark that does would break.
5. **Security claim corrected.** The research summary cited GHSA-9cfx-96xx-wmh9 (rio-tiler < 7.9.6) as a reason to
   retire legacy. The PyPI vulnerability feed lists **nothing** for rio-tiler 6.8.0, 7.9.5 or 7.9.6, or for
   titiler-core 0.18.6 or 0.22.4. pip-audit on the wrapper's pinned requirements finds no known vulnerability. OSV and
   the GitHub advisory page were unreachable (proxy 403). So the advisory is **unconfirmed** and is not a reason here.
   Retirement rests on items 1–4 alone.

## Not measured (stated, not hidden)

- The images themselves, their GDAL builds, or their pinned dependency sets. Auditing a venv is not auditing the image.
- MinIO/S3 reads, `file://` behaviour under the deployed volume layout, and concurrency or memory.
- Real production COGs, and any client outside this repository.
- Whether `TITILER_URL` on Railway is overridden to the legacy service. Variable values are not read in this session.
