# Agent B — recipe unit bridge and manual irrigation UI

Baseline: `239c01a47442df13d9cbb492017afae103b98dc8` in `/workspace/scratch/881ca3efb91d/sahool`.
Working source: shared integration worktree `/workspace/scratch/881ca3efb91d/sahool-unified`; no agent staging or commits.

## OXIDE-ELEMENT-UNIT-BRIDGE-NOT-WIRED-01

Source-level fixed, not production verified. The existing Phase 6 prescription generator route now exposes explicit recipe-input mass metadata using the same P2O5→P 0.4364 / K2O→K 0.8301 factors extracted into a pure nutrient-unit module. Original rate/unit remain intact. Elemental input is never converted twice. No inferred kg/ha basis for unlabeled material; invalid/nonfinite/negative/bool quantities rejected; explicit zero stays zero. `concentration_mg_l` remains null (no approved injection-window water volume); `execution_authorized=false`, `requires_agronomist_review=true`. No fertigation dispatch or lifting of quarantine.

Red: `oxide-red.log`: three missing recipe_input failures on baseline, seed control passes. Original witness copy `test_recipe_element_bridge.py` is the initial 4-case witness.
Green: `oxide-green.log`: 45 passed, 0 skipped — final 21 bridge cases, 18 existing fertigation/quarantine cases, 6 existing Phase 6 cases. Ruff check and format passed on all five Python paths.

Changed source:
- shared/precision_agriculture/nutrient_units.py (new)
- shared/precision_agriculture/phase6_intelligence.py
- shared/precision_agriculture/fertigation_plan.py (compatibility re-exports only)
- services/sahool-platform/api/routers/gis_cloud_native.py (invalid recipe ValueError→HTTP422)
- tests_v9/test_recipe_element_bridge.py (new)

## IRRIGATION-SLICE-HAS-NO-UI-CALLERS-01

OPEN — partial implementation only. The field workspace has explicit submit/review/plan/create controls and all three missing API callers, with separate actions and stable idempotency keys. Candidate field/season/version/review are checked; server proof and plan identity must match; missing, malformed, expired and mismatched water/source inputs fail closed; UI never synthesizes target volume, system or water digest. Parent keys creation component by field and season, so switching context resets state.

Current live candidate producer does NOT emit `manual_execution_source` (system, volume, water truth digest, window), so current candidates show the missing-source explanation and cannot progress to plan creation. The complete-source test is explicitly a contract fixture, not an assertion that the producer exists.

Additional independent-review limitation: reviewed decision / created plan progress is only held within the mounted component. Reload loses that step, and the pending-only queue cannot rehydrate approved decisions or saved plans. An authoritative approved-decision/plan lookup is still required; no browser persistence was used as proof.

Red: `irrigation-red.log`: 3 rendered UI tests fail on baseline because controls do not exist (not import/collection failure); witness preserved as `irrigation-red.test.tsx`.
Green: `irrigation-green.log`: 15 passed (3 rendered workflow cases + 12 client boundary cases), 0 skipped. TypeScript full project `tsc --noEmit -p frontend/tsconfig.json` exit 0 (`typecheck.log` empty). No browser/live-service acceptance claimed.

Changed source:
- frontend/src/services/api/irrigationManualCreation.ts (new)
- frontend/src/services/api/irrigationManualCreation.test.ts (new)
- frontend/src/sections/IrrigationManualCreationPanel.tsx (new)
- frontend/src/sections/IrrigationManualCreationPanel.test.tsx (new)
- frontend/src/sections/IrrigationManualOperationsPanel.tsx (2-line wiring)
