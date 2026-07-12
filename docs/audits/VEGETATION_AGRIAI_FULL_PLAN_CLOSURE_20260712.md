# SAHOOL Vegetation + AgriAI Full Plan Closure

Date: 2026-07-12
Base: `sahool_de0c61d_integrated_verified.zip`

## Implemented

- Canonical `indicator-registry.v1` with observed/derived classification, bands, ranges, eligibility, provenance and valid-pixel requirements.
- Deterministic vegetation feature manifest generation.
- Strict NDVI authority gate requiring raster ownership, scene, acquisition time, algorithm version, QA-mask version, availability time, quality score and valid-pixel percentage.
- Production-safe field-source policy: the synthetic legacy field registry is disabled by default in production.
- Current-NDVI endpoint fails closed in real-only mode; `all_fields` no longer uses the synthetic registry in production.
- Crop-card adapter with cultivar/version binding and deterministic parameter-set hash.
- Soil hydraulic adapter with FC/WP validation and available-water calculation.
- Daily weather-series adapter requiring temperature, rain, radiation and wind per day.
- Irrigation-event adapter applying system efficiency and producing an input hash.
- Point-in-time field-history composer excluding records not available by decision time.
- AgriAI context normalization now uses governed adapters rather than passing generic dictionaries unchanged.
- `AGRIAI_PRODUCTION_MODE` makes PCSE/WOFOST and complete scientific inputs mandatory; deterministic fallback is development-only.
- Migration `018_agronomic_context_snapshots.sql` adds immutable agronomic, vegetation and field-history snapshot stores with hashes, indexes, append-only triggers and tenant RLS.
- New CI closure gate plus updated production gate.

## Validation performed

- Python compileall: PASS
- Vegetation service tests: 39 passed
- AgriAI engine tests: 10 passed
- Vegetation/AgriAI production gate: PASS
- Vegetation/AgriAI full closure gate: PASS

## Honest remaining certification work

The repository-side gaps covered by this increment are closed. External certification still requires a staging environment with real Sentinel COGs, real PostgreSQL migration execution, real crop-card parameter sets, real soil/water/weather histories, PCSE installed, and field-measured yield/outcome datasets. Those are deployment and scientific-calibration evidence, not code that can be truthfully manufactured in an offline archive.

---

## Integration note (landed shape) — appended by the integrating session

The delivered bundle was integrated as a delta onto the landed tip (post-AC-1), not
wholesale. Deviations, each verified locally:

1. **Migration reconciliation.** The bundle's `018_agronomic_context_snapshots.sql`
   collides with the already-landed `services/decision-service/migrations/018_ac1_agronomic_context.sql`
   (same table `decision_agronomic_context_snapshots`, incompatible columns; the landed
   AC-1 store additionally carries idempotency/request-hash/replay semantics and
   append-only enforcement, and is wired to a real composer + decision binding).
   The bundle's variant — including its `decision_vegetation_snapshots` and
   `decision_field_history_snapshots` tables — has **no writer or reader anywhere in the
   bundle**; landing unwired duplicate stores is debt, not closure. It was therefore not
   landed. A first-class immutable vegetation-evidence store in decision-service is
   recorded as an open design item (`sahool-brain/gaps/registry.md`) to be landed
   together with its writer (vegetation→decision binding, master-plan Phase B/C).
   The full-closure gate asserts the landed `018_ac1_agronomic_context.sql` instead.
2. **Registry wiring fixed.** The bundle's `routers/analysis.py` registry endpoints
   reference `main.INDICATORS` / `main.REGISTRY_VERSION` / `main.indicator_definition`,
   but the bundle did not touch the service `main.py`, so those endpoints would raise
   `AttributeError` at request time. The landed shape re-exports the registry symbols
   from `main.py` (same decomposition pattern as the other `main.X` dependencies).
3. **`recl` registered.** The runtime emits `recl` (legacy red-edge chlorophyll id,
   also a distinct entry in `config/indicators_registry.json`); the bundle registry
   only knew `reci`, so `build_feature_manifest` would raise `KeyError` and crash
   snapshot building on the live analyze path. `recl` is registered and the manifest
   builder classifies unregistered names honestly (kind="unregistered", never
   decision-eligible) instead of crashing.
4. **Honest valid-pixel mapping.** raster-service's `ValidatedIndicatorProduct` carries
   `valid_pixel_ratio` (0..1); the registry authority check requires `valid_pixel_pct`
   (0..100). The runtime now performs the unit conversion only when the ratio is real —
   never invented. Note (open gap): raster provenance today publishes
   `capture_datetime`/`processing_version` and no `qa_mask_version`, so the strict
   authority gate will honestly fail-closed in production real-only mode until raster
   provenance is enriched — recorded as RASTER-PROVENANCE-ENRICHMENT.
5. **Crop-card adapter engagement.** `normalized_engine_inputs` engages the strict
   crop-card adapter when a versioned card is supplied (`version` present); sparse
   legacy `crop_parameters` keep the pass-through shape instead of turning a legacy
   request into an unhandled 500.
6. All delivered code was re-formatted to the repository ruff style; the delivered
   compact one-liner style fails `ruff format --check` as shipped.
