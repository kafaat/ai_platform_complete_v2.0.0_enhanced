# CDSE native QA and vegetation contract repair

Base `6e8cc0f9952c037550ae1644919f88c475dd89a7`. This is source/fixture evidence,
not a live CDSE, PostgreSQL or production acceptance report.

The internal field/backfill CDSE request now asks for a four-band TIFF (unmasked
index, SCL, dataMask, contributor ordinal) and returned scene metadata in one TAR.
The parser reads only two bounded regular in-memory members, never extracts paths,
and binds the TIFF bytes to the exact evalscript digest. The raster producer
applies native SCL/dataMask locally and records actual counts. A catalogue choice,
requested mask, requested day, old raster, missing metadata or changed TIFF cannot
stand in for observed mask execution. Multiple contributing source tiles are
rejected rather than called a single scene. True-color and display-tile requests
retain their existing path; native indicator provenance applies to new field and
backfill products only.

The producer replaces request/catalogue scene guesses with the single returned
contributor's identity and aware acquisition time. Measured pixel QA travels in
`quality_score` with `sahool.raster_pixel_qa/1` semantics; legacy `confidence` stays
separate. Persistence carries actual algorithm/mask identity and measured receipt.
Canonical observations add optional typed pixel-owner lineage separately from the
indicators-service publisher. Vegetation validates that contract and tenant/field/
season before accepting original raster authority. Missing lineage still returns
424. Nonfinite, boolean or out-of-range quality/coverage cannot open the gate.
No threshold was lowered.

## Evidence

- Frozen final tests against untouched pinned-main source: 19 quality failures and
  4 canonical lineage/scope failures. `red-replay.json` records exact test hashes.
- Final focused pipeline: **82 passed, zero failed/skipped**. Actual rasterio,
  COG writing, layer/bundle production, canonical serialization and vegetation
  production gate execute. HTTP is a native TIFF/TAR fixture. SQL is not live.
- Related CDSE and contract regressions: **286 passed**.
- Vegetation service plus producer regressions: **98 passed** with an explicit
  local-only assertion key. Without that test configuration one pre-existing
  field-catalog test fails identically on main; its baseline log is retained.
- All 20 native evalscripts executed locally in Node. This does not assert that
  CDSE ran them; the provider's native QA is applied locally only after receipt.

## Historical empty-scene case remains open

The accessed committed reports, PR1182 description and review comment6168991949
all explicitly state that original historical bytes were discarded. No historical
cause was recovered. The existing rolling failure receipt recorder cannot recover
an unrecorded earlier event. No production rows or historical assets were queried
or relabelled by this work.

Concrete disposition available to the operator: retain the original incident and
metadata with `unknown_evidence_not_recorded`; keep legacy products without native
QA proof ineligible; regenerate under the new measured path as a **new** product
identity, retaining its receipt separately. This is prospective remediation, not
recovery of the original cause. A formal acceptance of evidence loss would be an
owner administrative disposition, not a fabricated `verified` technical result.

## Provider protocol references

- https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/UserGuides/Metadata.html
- https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Evalscript/Functions.html
- https://documentation.dataspace.copernicus.eu/notebook-samples/sentinelhub/getting_started/data_download_process_request.html

These document TILE scene metadata through `updateOutputMetadata` and multi-output
TIFF/JSON TAR responses. The tests use this protocol but are not live provider proof.
