# Soil Final Plan P0 — Durable Lab & Projection · Integration Note (landed shape)

Integrated `sahool_soil_final_plan_p0_durable_lab_projection_20260713.zip` onto the landed
tip (post RIV runtime-truth + container fixes). Methodology: take the true soil delta; keep
my container/RIV/security fixes (the bundle's base predated them); fix delivered bugs.

## Genuine soil delta adopted
- migrations **v155** (canonical `soil_observations` + immutable `soil_profile_snapshots`) and
  **v156** (durable `lab_samples` + `lab_sample_custody_events` + immutable `soil_lab_results` +
  `water_lab_result_sets`), registered in run_migrations.sql (161/162) + MANIFEST.
- New contracts `shared/contracts/soil/` (observation/profile/use_policy + 2 JSON schemas).
- soil-service: `soil_store.py`, `profile_composer.py`, `evidence_adapters.py`,
  `routers/canonical.py`; `readings.py` now reads canonical `soil_observations` (dual-writes
  legacy + canonical + rebuilds snapshot under a per-tenant/field advisory lock, profile-hash idempotent).
- platform: durable `lab_store.py` + `soil_evidence_bridge.py`; `soil_sampling.py` lab
  sample/custody/transition workflow (requested→sampled→in_lab→result_received→approved→published);
  on publish, approved analytes POST to the canonical soil evidence endpoint.
- decision-service: `validate_soil_use` dispatch gate + readyz `canonical_soil_profile_required`.
- agronomic context: validates `soil_profile` snapshot (agriai + decision PIT).
- 5 new CI guards: soil_profile_contract / soil_canonical_store / soil_full_chain /
  soil_lab_projection / vegetation_runtime_truth (RIV regression guard).

## Kept mine (bundle base was stale — would have reverted these)
vegetation/indicators/decision main.py container fixes, VEGETATION_REAL_ONLY export,
indicators `_resolve_manifest`, the p1/consumer/vegetation-container guards, and the RIV
observation-bundle tests + runtime-truth. readings.py field-ownership authz preserved.

## Delivered bugs fixed
1. **v155 broken RLS** — `FORCE ROW LEVEL SECURITY` without `ENABLE` and no policy on
   `soil_observations`/`soil_profile_snapshots` (inspector flagged 2 tables). Added explicit
   ENABLE + FORCE + `tenant_isolation` policy mirroring v156.
2. **v156 unregistered** — bundle's run_migrations.sql registered only v155; added v156 (step 162).
3. **decision Dockerfile** — the soil import needs `COPY shared/`; taken from the bundle Dockerfile.
4. **endpoint-UI coverage** — lab `.../transition` route escaped the contract; added an
   `operational` no-UI waiver.
5. ruff E402/B017 in bundle files; unused imports.

## Compose enforcement posture (deliberate deviation for the live stack)
Contract guards mandate production-safe compose defaults (`AGRIAI_STRICT_CONTEXT`,
`DECISION_REQUIRE_AGRONOMIC_CONTEXT`, `DECISION_REQUIRE_SOIL_PROFILE` = `:-true`). The
**dispatch-blocking** `DECISION_REQUIRE_SOIL_EVIDENCE_GATE` is kept `:-false` (least-surprise
on a live stack). `.env.example` documents all four as `false`. **Operator note:** on a stack
without populated agronomic context / soil profiles, set
`DECISION_REQUIRE_AGRONOMIC_CONTEXT=false`, `DECISION_REQUIRE_SOIL_PROFILE=false`,
`AGRIAI_STRICT_CONTEXT=false` in `.env` to avoid fail-closed decisions/agriai until data exists.

## Verification (landed shape)
- `pytest -m unit`: **2914 passed**, 5 skipped.
- soil-service 29 · platform lab 1 · decision soil-context 2 · agriai context 6 — pass.
- Guards: 5 soil + p1/consumer/vegetation-container/veg-agriai-closure/riv/compose-env — all pass.
- 4 inventory guards + route_mount + runtime_real_smoke_ok + release validate (4138 checksums).
- ruff check/format clean.

## Deferred (honest — needs live Docker/PostgreSQL)
Runtime certification of v155/v156 on real PG16: cross-tenant RLS negative tests, concurrent
duplicate result/profile-rebuild, real network publish platform→soil-service, restart/crash
recovery. And the broader roadmap (SoilGrids adapter, mobile imaging, analog engine, spatial
products, hydraulic/irrigation-water/drainage/reclamation) — subsequent increments.
