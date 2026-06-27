# Full Agricultural Season Forensic Trace — Farm Operations Ledger

## Scope
Verified a complete wheat season flow across the pure Farm Ledger core:

1. Season budget by growth/operation stage
2. Daily operation records
3. Water, energy, equipment, labor, and input records
4. Operational summary
5. Actual-vs-budget variance analysis
6. Profitability calculation
7. AI-ready feature row
8. Cost recommendations
9. Inventory projection
10. ERP financial projection
11. Autowrite preview from operation event
12. Economic state projection

No database, inventory write, ERP write, or CanonicalFieldState write was performed. This preserves the current safety model.

## Scenario
- Crop: wheat
- Season: `wheat-2026`
- Area: 50 ha
- Unit: pivot field `field-pivot-01`
- Tenant: `tenant-aljawf`
- Stages covered: preparation, planting, vegetative, flowering, harvest, transport, packaging, storage, whole-season administration

## Verified Results

### Operational Summary
- Operations: 8 records
- Total cost: 40,500 YER
- Direct cost: 38,400 YER
- Indirect cost: 2,100 YER
- Water: 325,000 m³
- Energy: 21,500 kWh
- Equipment: 388 hours
- Labor: 112 hours
- Syncable cost: 10,100 YER

### Input Trace
- Seed: 9,000 kg
- Fertilizer: 14,000 kg
- Pesticide: 85 liter
- Packaging: 9,000 units

### Budget Variance
- Water at flowering: critical, +28.0%
- Fertilizer at vegetative stage: watch
- Pesticide at flowering: critical
- Labor at planting: actual cost without planned budget line, correctly flagged as plan/classification issue

### Profitability
- Revenue: 72,000 YER
- Total cost: 40,500 YER
- Gross margin: 31,500 YER
- Cost per ton: 192.85714285714286 YER
- Revenue per ton: 342.85714285714283 YER

### Economic State
- Cost per ha: 810 YER/ha
- Water per ha: 6,500 m³/ha
- Energy per water: 0.0662 kWh/m³
- Budget status: critical
- Profitability status: profitable
- Provenance confirms: prediction=false, canonical_state_write=false

### Projections
- Inventory projection is `projection_only`, disabled reason `feature_flag_off`.
- ERP projection totals 40,500 YER and is memoed as a financial projection only.
- Autowrite preview is eligible when field/season scope exists but remains non-persisted by provenance.

## Verification Commands

```bash
PYTHONPATH=services/sahool-platform python -m pytest -q \
  services/sahool-platform/tests/test_farm_operations_ledger.py \
  services/sahool-platform/tests/test_farm_costing.py \
  services/sahool-platform/tests/test_farm_closed_loop.py \
  services/sahool-platform/tests/test_farm_full_season_forensic.py
```

Result: `14 passed`

```bash
python -m compileall -q \
  services/sahool-platform/core/farm_operations_ledger.py \
  services/sahool-platform/core/farm_costing.py \
  services/sahool-platform/core/farm_closed_loop.py \
  services/sahool-platform/api/routers/farm_operations_ledger.py \
  services/sahool-platform/tests/test_farm_full_season_forensic.py
```

Result: `passed`

```bash
PYTHONPATH=services/sahool-platform python - <<'PY'
import importlib
for m in ['core.farm_operations_ledger','core.farm_costing','core.farm_closed_loop']:
    importlib.import_module(m)
    print('IMPORT_OK', m)
PY
```

Result: all imports OK.

```bash
python tools/sahool_inspector.py
```

Result: `PASS`.

## Honest Limits
This test verifies the full season flow in pure core logic and static platform checks. It does not perform a live DB/API/mobile/ERP integration run. Those require a running environment with Postgres, API service, tenant context, and optionally ERP/inventory services.
