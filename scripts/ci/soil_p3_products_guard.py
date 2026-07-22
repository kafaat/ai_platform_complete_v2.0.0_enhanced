#!/usr/bin/env python3
from pathlib import Path

root=Path(__file__).resolve().parents[2]
required=[
 'shared/contracts/soil/p3.py','services/soil-service/p3_products.py','services/soil-service/p3_store.py',
 'services/soil-service/routers/p3_products.py','services/soil-service/test_soil_p3_products.py',
 'migrations/v163_soil_p3_assessment_products.sql']
missing=[p for p in required if not (root/p).exists()]
assert not missing, f'missing P3 files: {missing}'
contract=(root/'shared/contracts/soil/p3.py').read_text()
for token in ['reference_card_detected','minimum_cohort_size','surveyed_elevations','risk_adjusted_npv']:
 assert token in contract, token
migration=(root/'migrations/v163_soil_p3_assessment_products.sql').read_text()
for table in ['soil_visual_observations','soil_analog_products','soil_drainage_assessments','soil_reclamation_assessments','soil_reclamation_economics']:
 assert table in migration and 'FORCE ROW LEVEL SECURITY' in migration
router=(root/'services/soil-service/routers/p3_products.py').read_text()
for route in ['mobile-images/analyze','analog-estimate','drainage-assessment','reclamation-assessment','reclamation-economics']:
 assert route in router, route
print('soil_p3_products_guard_ok')
