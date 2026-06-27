# SAHOOL — Full Agricultural Season Lifecycle Forensic Simulation

## Scope

This audit adds and runs a deterministic, no-external-I/O test that simulates a complete agricultural season across the platform control layers:

Field creation → lab readiness → crop card and phenology → satellite indicators → sensors → weather → irrigation engine → season budget → field operations → daily ledgers → variance → profitability → recommendations → inventory projection → ERP projection → economic state → yield interval → previous-season comparison.

## Added test

`services/sahool-platform/tests/test_platform_agri_full_lifecycle_forensic.py`

The test uses existing SAHOOL core modules:

- `core.field_lifecycle`
- `core.soil_recommendations`
- `core.sensor_intake`
- `core.season_phenology`
- `core.engines.fao56`
- `core.farm_operations_ledger`
- `core.farm_costing`
- `core.farm_closed_loop`
- `core.yield_interval_service`
- `core.season_comparison`

No database, ERP write, inventory write, or CanonicalFieldState write is performed. The test verifies projection/control behavior only.

## Simulated season

- Tenant: `tenant-aljawf`
- Farm: `farm-alhazm`
- Field: `field-pivot-barley-01`
- Crop: `barley`
- Season: `barley-2026`
- Area: `42 ha`
- Irrigation: center pivot
- Geometry source: geodesic pivot drawing
- Boundary confidence: `0.93`

## Verified chain

### 1. Field creation and geometry

The simulation verifies a field record with:

- tenant scope
- farm scope
- field ID
- pivot center
- pivot radius
- area
- boundary confidence

### 2. Soil/water lab readiness

The test verifies `resolve_state(PROVIDED, {S3,S4,I3})` returns:

- `READY`
- enables irrigation, fertility, and salinity management classes of recommendations

The test also passes soil pH and texture through `soil_to_recommendations`.

### 3. Crop card and phenology

The test verifies:

- crop card loading for `barley`
- four growth stages
- current stage at DAS 70 = `mid`
- Kc at DAS 70 = `1.15`

### 4. Satellite indicators and layer switching

The simulation models dated raster assets for:

- NDVI
- NDMI
- MSI

The test asserts exact date + indicator selection and prevents silent fallback to `latest` for a user-selected date/indicator combination.

### 5. Sensors

The test ingests a batch of sensor readings:

- soil moisture
- soil EC
- air humidity

All are accepted and converted to observations with source `sensor`.

### 6. Weather and irrigation engine

The test runs FAO-56 irrigation calculations for multiple days after sowing using:

- WeatherDay
- barley crop Kc profile
- loam SoilZone
- salinity disabled by default

It verifies mid-season irrigation requirement exceeds establishment-stage requirement and that salinity remains opt-in/off.

### 7. Season budget

The test builds budget lines by stage and category:

- preparation
- planting
- development
- mid-season irrigation/fertilization/pest control
- harvest
- transport
- storage
- whole-season administration

### 8. Field operations and daily ledgers

The simulation records operations:

- land preparation
- planting
- fertilization
- irrigation
- pest control
- harvest
- transport/storage
- administration

It links water, energy, equipment, labor, and input records.

### 9. Variance and recommendations

The test computes actual-vs-budget variance and verifies:

- water variance is flagged as watch/critical
- pesticide actual exceeds plan
- cost recommendations require human review and declare provenance

### 10. Inventory and ERP projections

The test verifies:

- inventory projection is `projection_only`
- disabled reason is `feature_flag_off`
- ERP lines are grouped by category but not posted

### 11. Economic state and AI features

The test verifies:

- profitable season summary
- water per hectare
- AI feature row provenance declares `prediction=False`
- economic state declares `canonical_state_write=False`

### 12. Yield and previous-season comparison

The test verifies:

- conformal yield interval returns calibrated interval with enough residuals
- comparison with previous barley season shows yield improvement

## Verification commands

```bash
cd services/sahool-platform
PYTHONPATH=. pytest -q \
  tests/test_platform_agri_full_lifecycle_forensic.py \
  tests/test_farm_full_season_forensic.py \
  tests/test_farm_operations_ledger.py \
  tests/test_farm_costing.py
```

Result:

```text
11 passed
```

Additional checks:

```bash
python -m compileall -q services/sahool-platform/core services/sahool-platform/tests/test_platform_agri_full_lifecycle_forensic.py
python tools/sahool_inspector.py
```

Result:

```text
compileall passed
sahool_inspector.py PASS
```

## Honest limitations

This is a deterministic forensic simulation of core platform logic, not a live deployment test. The following remain runtime/environment checks:

- real user → nginx → service → DB journey
- live Postgres RLS leakage attempt
- live NATS publish/consume flow
- live raster download/COG generation against real satellite providers
- live tile rendering in browser
- Flutter mobile notification/offline sync journey

## Conclusion

The tested platform control layer can execute a complete agricultural season trace from field creation through harvest economics and previous-season comparison without external side effects. All financial, inventory, ERP, and canonical-state writes remain projection-only unless explicitly enabled by feature flags.
