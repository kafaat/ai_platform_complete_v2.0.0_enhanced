# Soil P1 Governed Products — Integration Note (2026-07-13)

Integrates the P1 bundle (`sahool_279651d_soil_p1_complete`) onto the landed soil chain
(tip `bc0301e`, v155–v160). P1 adds four governed soil products behind stable product
identities, migration **v162→v161** (5 tables), auto-discovered router, and a CI guard.

## Adopted
- `shared/contracts/soil/p1.py`: SoilGrids spatial product, sampling plan/candidate/point,
  hydraulic value/layer/profile, irrigation-water sample/profile; `EvidenceOrigin`
  (measured / pedotransfer / modelled). Exported via `shared/contracts/soil/__init__.py`.
- `services/soil-service/p1_products.py` (pure builders), `p1_store.py` (durable, RLS),
  `routers/p1_products.py` (soilgrids-spatial, sampling-plans + approve, hydraulic-profile,
  irrigation-water) — auto-mounted by the pkgutil router registry.
- Composer: layer `uncertainty` now carried from provenance.
- Migration `v161_soil_p1_products.sql`: soil_spatial_products, soil_sampling_plans,
  soil_hydraulic_profiles, irrigation_water_samples, irrigation_water_profiles — all
  ENABLE+FORCE RLS with tenant_isolation; stable product identity (tenant+field+type+
  version+geometry_hash) prevents needless SoilGrids re-creation.

## Real-PostgreSQL certification (this session)
v161 applied cleanly to the migrated cert DB; all five tables confirmed ENABLE+FORCE RLS
with a `tenant_isolation` policy. soil-service suite 46 passed (incl. 3 P1 tests).

## Delivered defects fixed
- P1 modules used `from shared.contracts.soil import *` (F403/F405), a loop-closure over
  `p` (B023), and ambiguous `l` names (E741) — all would fail CI `ruff check`. Replaced the
  star import with explicit imports, bound the closure via default arg, renamed loop vars.

## Governance honesty (unchanged intent)
SoilGrids stays `evidence_class = modelled` (never measured); pedotransfer hydraulics are
labelled `pedotransfer`, direct measurements win; unapproved/incomplete water samples remain
advisory and block gypsum_rate / automatic_irrigation_execution / reclamation_execution.
