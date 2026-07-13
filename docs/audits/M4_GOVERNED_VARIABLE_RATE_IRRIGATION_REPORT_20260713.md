# M4 — Governed Variable-Rate Irrigation (VRI) Completion Report

Date: 2026-07-13

## Scope

M4 converts a governed hourly MPC water budget into a spatial, recommendation-only VRI prescription. It consumes canonical management-zone water state, EO stress, terrain/infiltration evidence, machine geometry, sprinkler/runoff limits, the unified irrigation capability graph, and the commissioning executability gate.

## Added artifacts

- `services/sahool-platform/api/canonical_vri_prescription.py`
- `migrations/v179_governed_vri_prescription.sql`
- `tests_v9/test_canonical_vri_prescription.py`
- `scripts/ci/irrigation_vri_m4_guard.py`

## Governed contracts

- `VRIPrescriptionZone`
- `GovernedVRIPrescription`
- `build_governed_vri_prescription()`
- `vri_prescription_to_translation_input()`

The prescription is always:

- `recommendation_only=true`
- `execution_allowed=false`
- `translation_allowed=false`

The neutral translation input is also `dispatch_allowed=false`.

## Allocation policy

The engine preserves the M3 water budget where hard constraints permit. Allocation uses root-zone depletion as the primary signal and EO stress as a bounded secondary signal. Excluded zones receive zero. Each zone is capped by the lowest governed application limit from machine, sprinkler/runoff and zone evidence.

EO evidence cannot independently create irrigation demand where root-zone depletion is absent.

## Fail-closed conditions

The engine blocks on missing or invalid:

- M3 schedule and schedule digest
- capability graph and capability digest
- commissioning executability gate
- management-zone-set, machine-geometry, sprinkler and terrain digests
- zone identity, area or angular/radial geometry
- zone root-water state
- EO stress evidence
- terrain/infiltration evidence
- zone runoff/application cap
- machine coverage area

It also blocks when aggregate zone area exceeds machine area or no eligible application zone remains.

## Persistence and tenancy

Migration `v179` adds:

- `vri_prescriptions`
- `vri_prescription_zones`
- `vri_machine_translation_artifacts`
- `vri_as_applied_variances`

All tables use tenant-bound keys, `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and tenant `USING` plus `WITH CHECK` policies. Database checks prevent execution, translation or dispatch flags from being set true in M4.

## Verification

Focused M4 tests:

- 8 passed
- 0 failed
- deprecation warnings treated as errors

Cross-stage irrigation regression:

- 122 passed
- 0 failed
- 0 `DeprecationWarning`

CI ratchets verified:

- M2.1 through M2.11 guards: PASS
- M3 guard: PASS
- M4 guard: PASS
- FastAPI lifespan guard: PASS
- Python compilation: PASS

## Explicit non-claims

This environment did not certify:

- applying `v179` to live PostgreSQL
- live tenant-isolation/RLS behavior
- polygon topology or raster-to-zone generation
- vendor-specific VRI file translation
- controller upload or dispatch
- live as-applied spatial comparison
- field calibration of application-percent behavior

The current geometry contract is neutral angular/radial segmentation suitable for center-pivot and sector-pivot prescriptions. Polygonal and linear-move translation remains a later adapter concern.

## Next stage

M5 — Closed-Loop Learning and Production Certification:

`recommendation → approval → execution → receipt → as-applied truth → water-state reconciliation → outcome → governed learning`
