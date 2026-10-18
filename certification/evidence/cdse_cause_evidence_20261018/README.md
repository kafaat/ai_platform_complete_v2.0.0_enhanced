# CDSE empty outcomes: a cause only from catalogue evidence (2026-10-18)

**Gap:** `CDSE-EMPTY-SCENE-HAS-NO-ATTRIBUTABLE-CAUSE-01`. It stays **open**: the historical incident is not
reconstructed, and nothing here ran against the live provider.

## What existed before this change

`services/raster-service/cdse_diagnostics.py` already wrote bounded failure receipts.
- Attribution was `unknown` unless an HTTP status, a transport failure or polygon-mask counts said otherwise.
- `catalogue_evidence` was always `not_available`.
- The catalogue search applies the tile cloud filter (`eo:cloud_cover <= 40`), so an empty answer cannot tell
  "no acquisition" from "every acquisition was too cloudy".
- On the interactive path the evalscript writes `NaN` for both no-data and cloud (`cdse_client.py:458`), so zero
  observable pixels cannot separate them either.

## What changed

1. **Catalogue probe.** `raster_cdse_tile_runtime.catalogue_probe`, used on `empty_raster` and `no_selected_scene`
   only, runs one catalogue search over the failed window with the cloud filter lifted (`max_cloud_pct=100`) and no
   transport retries.
   - Answers are reused for 300 s per window, with at most 256 entries, so a field whose tiles keep failing does not
     turn every tile into a provider call.
   - The probe is **off unless `CDSE_DIAGNOSTIC_CATALOGUE_PROBE=1`**, because it adds a provider call. Turning it on
     is a Railway variable change and needs the owner's approval.
   - It lives in the tile runtime, a gate-guarded chokepoint. `test_imagery_source_gate_no_bypass_static` rejected it
     in `cdse_diagnostics.py`, and the allowlist was not widened.
2. **Evidence values:** `no_acquisition`, `acquisitions_above_cloud_limit`, `acquisitions_within_cloud_limit`,
   `acquisitions_cloud_cover_unknown`, `catalogue_unavailable`, and `not_available` (not asked).
   - A failed search is `catalogue_unavailable`, never "no acquisition".
3. **Attribution, only while it is still `unknown` and only for those two outcomes:**
   - `no_acquisition` → `no_acquisition_in_window`
   - `acquisitions_above_cloud_limit` → `filtered_by_tile_cloud_cover`

   Every other combination stays `unknown`, including a scene within the limit that produced zero pixels. HTTP-status
   and polygon-mask attributions keep precedence.
4. **Backfill:** `cdse_native_product.decode_response` raises `CdseNoContributingScene` (a `ValueError`) when CDSE's
   `userdata.tiles` is empty, instead of `cdse_native_tiles_invalid`.
   - This is the provider's own statement that no tile passed `timeRange` + `maxCloudCoverage=40`. It happens when the
     day comes from an Element84 scene and CDSE has nothing under its own filter for that day.
   - The backfill item error then reads `exception:CdseNoContributingScene:<id>` instead of `exception:ValueError:<id>`
     (`backfill_scan_worker.py:822`). That is from reading the code, not from a test.
   - Failure behaviour is unchanged: it still fails closed.

## Probes (injected clients, no live provider)

[`probe_results.txt`](probe_results.txt) lists the 25 passing cases in `services/raster-service/test_cdse_cause_evidence.py`.

| Probe | Expected |
|---|---|
| P1 no acquisition in the window | `no_acquisition` → `no_acquisition_in_window` |
| P2 acquisitions only above 40% | `acquisitions_above_cloud_limit` → `filtered_by_tile_cloud_cover` |
| P3 scene within the limit, zero pixels; or cloud cover unknown | evidence recorded, attribution `unknown` |
| P4 pixels before the polygon mask, none after | `polygon_mask_removed_observations`, even with `no_acquisition` |
| P5 catalogue outage; probe disabled | `catalogue_unavailable` / `not_available`, attribution `unknown`; disabled asks nothing |
| P6 provider 429 | `rate_limited`, no probe |
| P7 processing-baseline offset | no probe: it changes values, it does not empty a raster |
| P8 valid raster | no receipt, no probe |

**Manual mutations, each turned the suite red, then restored:**
- drop the `no_acquisition` mapping
- read an outage as absence
- treat empty tiles as invalid
- probe always on
- no probe cache
- catalogue overriding the mask attribution
- probe with retries
- `<` instead of `<=` at the cloud limit

**Regression:** the existing CDSE receipt and native-product suites and the source-gate bypass guard pass unchanged
(111 passed together with the new file). The whole
raster-service suite has 637 passed and 2 failed. The 2 failures are in `test_raster_router_decomposition_guard.py`,
which needs `python-multipart`; it is absent in this container, and the tree without this change fails the same way.

## Not measured (stated, not hidden)

- **No live CDSE call.** Whether the probe's evidence matches what Process API saw for the same window is an inference
  from both using tile-level cloud cover on the same collection. Ingestion lag between catalogue and processing is
  possible.
- **Cloud versus no-data** inside a scene that passed the filter is still not separable on the interactive path. That
  needs a change to the rendered evalscript output, which is a separate decision.
- Nothing here reconstructs the historical incident.
