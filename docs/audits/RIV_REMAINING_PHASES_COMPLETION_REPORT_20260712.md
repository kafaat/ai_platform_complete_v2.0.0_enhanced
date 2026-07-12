# RIV Remaining Phases Completion Report — 2026-07-12

## Scope
Completion of Raster–Indicators–Vegetation consolidation after RIV-P0.

## Completed phases

### RIV-P1 — Canonical Indicator Contract and Registry Generation
- `config/indicators_registry.json` remains the single authoring source.
- Added `scripts/ci/generate_indicator_artifacts.py`.
- Generated artifacts:
  - `services/sahool-platform/api/indicator_catalog.generated.json`
  - `services/vegetation-analysis-service/indicator_capabilities.generated.json`
  - `frontend/src/lib/indicatorsRegistry.generated.ts`
- `--check` mode fails CI on drift.
- Added canonical observation JSON Schema:
  `shared/contracts/indicator_observation.schema.json`.

### RIV-P2 — Consumer and ownership flow
- Added `shared/contracts/indicator_product_flow.json`.
- Declares producer, consumers, storage owner, and fallback policy for:
  observed indicators, vegetation interpretation, and dashboard aggregation.
- Platform dashboard catalog now loads generated metadata, not a handwritten list.
- Vegetation registry now loads generated capabilities and retains stable validation APIs.

### RIV-P3 — Duplicate computation removal
- Removed direct Sentinel-Hub evalscript/band-math from vegetation runtime.
- Removed deterministic synthetic bands and `_compute_indices` from vegetation.
- Vegetation now requests validated Raster products only and returns HTTP 424 if real NDVI is absent.
- Removed Platform band-math expressions; map-layer metadata identifies Raster as authority.
- Converted `vegetation_index_explorer` from a local spectral calculator to a fail-closed Raster boundary adapter.
- RIV boundary guard tokenizes Python and blocks executable spectral formulas outside Raster.

### RIV-P4 — Vegetation interpretation boundary
- Vegetation consumes real NDVI/EVI/MSAVI/NDMI/MSI/NDWI/GNDVI products.
- LAI is explicitly derived from validated NDVI with uncertainty/provenance.
- Added `water_stress` interpretation based on observed NDMI/MSI; it is not a spectral kernel.
- CWSI and RECl synthetic paths are marked not implemented.
- Recommendations remain hypotheses and explicitly delegate execution decisions to Decision-Service.

### RIV-P5 — Raster efficiency and dedup foundation
- Added `services/raster-service/indicator_product_identity.py`.
- Product identity includes:
  `tenant_id + field_geometry_hash + scene_id + indicator + algorithm_version + qa_mask_version`.
- Added deterministic SHA-256 product keys.
- Added ordered multi-indicator batch planning with duplicate removal.
- This provides the contract for one scene read / multiple products and storage-level idempotency.

### RIV-P6 — CI ratchets
- Added `scripts/ci/riv_boundary_gate.py`.
- Updated `.github/workflows/ci.yml` to run:
  - generated-artifact sync;
  - RIV ownership and formula boundary gate.
- Existing indicator registry and consumer contract guards remain green.

## Verification

Focused and expanded suite:

```text
62 passed
```

Additional checks:

```text
indicators_registry_gate_ok (34 indicators, 19 renderable)
riv_boundary_gate_ok
consumer_contract_gate_ok
indicator_artifacts_ok
py_compile passed
```

## Ownership after consolidation

| Product | Owner | Consumers |
|---|---|---|
| Observed spectral products | raster-service | vegetation, platform, web, mobile, decision |
| Vegetation health/trend/stress interpretation | vegetation-analysis-service | platform, web, decision |
| Cross-domain dashboard aggregation | sahool-platform | frontend |
| Indicator contract/catalog publication | indicators-service (contract-only) | developers/runtime discovery |

## Explicitly removed behavior
- Synthetic NDVI and related bands in Vegetation.
- Direct Sentinel provider pixel computation in Vegetation.
- Scalar spectral calculators in Platform operational tools.
- Hand-maintained Platform and Vegetation indicator catalogs.
- Platform-owned band-math expressions.

## Runtime work still requiring staging infrastructure
The code-level consolidation is complete. The following requires real infrastructure and is not claimed as executed here:
- PostgreSQL/S3/Redis runtime load test.
- Benchmark proving one COG read for a multi-index batch.
- Cache-hit and duplicate-job metrics under worker concurrency.
- Full web build/test where Node dependencies are installed.
- Soak test across CDSE backfill and interactive queues.

## Recommended runtime acceptance gates
- No duplicate persisted product for the same canonical product key.
- Batch processing opens source bands once per scene/window.
- Vegetation readiness fails when Raster is unavailable in real-only mode.
- All decision evidence contains scene, acquisition, QA mask, algorithm, and product versions.
- No frontend endpoint targets spectral computation on indicators-service.
