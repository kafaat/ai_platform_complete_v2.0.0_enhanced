from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
required=['migrations/v162_soil_p2_spatial_products.sql','shared/contracts/soil/p2.py','services/soil-service/p2_products.py','services/soil-service/p2_store.py','services/soil-service/routers/p2_products.py','services/soil-service/test_soil_p2_products.py']
missing=[x for x in required if not (ROOT/x).exists()]
assert not missing, f'missing P2 soil files: {missing}'
sql=(ROOT/'migrations/v162_soil_p2_spatial_products.sql').read_text()
for t in ['soil_bare_composites','soil_terrain_products','soil_texture_products','soil_salinity_products']:
    assert t in sql and 'FORCE ROW LEVEL SECURITY' in sql and 'WITH CHECK' in sql
code=(ROOT/'services/soil-service/p2_products.py').read_text()
for token in ['no_eligible_bare_soil_scenes','spatial_block','high_risk_actions_require_lab_verified','engineering drainage design requires surveyed elevations']:
    assert token in code
router=(ROOT/'services/soil-service/routers/p2_products.py').read_text()
for path in ['bare-soil-composite','terrain-derivatives','texture-probability','salinity-assessment']:
    assert path in router
print('soil_p2_products_guard_ok')
