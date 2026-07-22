#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
required=[
 'migrations/v161_soil_p1_products.sql','shared/contracts/soil/p1.py',
 'services/soil-service/p1_products.py','services/soil-service/p1_store.py',
 'services/soil-service/routers/p1_products.py','services/soil-service/test_soil_p1_products.py']
for f in required:
 assert (ROOT/f).is_file(), f'missing:{f}'
text=(ROOT/'migrations/v161_soil_p1_products.sql').read_text()
for table in ['soil_spatial_products','soil_sampling_plans','soil_hydraulic_profiles','irrigation_water_samples','irrigation_water_profiles']:
 assert table in text and 'FORCE ROW LEVEL SECURITY' in text
router=(ROOT/'services/soil-service/routers/p1_products.py').read_text()
for route in ['soilgrids-spatial','soil/sampling-plans','hydraulic-profile/rebuild','hydraulic-profile','irrigation-water/samples','irrigation-water/sources']:
 assert route in router, route
# quote/space-robust: SoilGrids evidence must be modelled, never measured (ruff normalises quotes+spacing)
_norm = router.replace(" ", "").replace('"', "'")
assert "'evidence_class':'modelled'" in _norm
print('soil_p1_products_guard_ok')
