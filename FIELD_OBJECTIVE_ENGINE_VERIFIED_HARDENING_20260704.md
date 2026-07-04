# Field Objective Engine — Verified Hardening (2026-07-04)

## Scope
Verified and hardened the uploaded `sahool_main_777582b_field_objective_engine.zip` implementation of the Field Objective Engine.

## Confirmed implementation
- `frontend/src/lib/fieldObjectiveEngine.ts`
  - Six objective intents:
    - `diagnose_field_stress`
    - `plan_irrigation_week`
    - `prepare_spray_window`
    - `create_vra_prescription`
    - `review_season_profitability`
    - `generate_field_report`
  - Evidence gating by source availability.
  - Inspect → reason → act → review objective steps.
  - Honest blocking when required evidence is missing.

- `frontend/src/lib/fieldActionLifecycle.ts`
  - Recommendation lifecycle state machine.
  - Explicit transitions only.
  - Evidence gate before recommendation approval.
  - Follow-up derived from objective metadata, not invented cadence.

- `frontend/src/components/fieldview/FieldObjectivePanel.tsx`
  - Expert-mode FieldView objective panel.
  - Objective picker.
  - Evidence readiness display.
  - Lifecycle controls.
  - MapHub integration.

## Hardening applied in this pass
The uploaded implementation had one practical UX/state-machine gap: objectives that do not produce a field task, such as VRA prescription, profitability review, or field report generation, could be approved but then had no lifecycle action to complete/review the output.

Fixed by:
- Adding `completed` as an explicit `Outcome`.
- Allowing `record_outcome` from `approved` to `reviewed` for non-task objectives.
- Treating `completed` as a good reviewed outcome.
- Adding Arabic label `مكتمل`.
- Adding a UI action: `سجّل المخرج كمكتمل` for non-task objectives.
- Adding a regression test to prevent non-task objectives from getting stuck after approval.

## Verification actually run
From `frontend/`:

```bash
npm ci --legacy-peer-deps --ignore-scripts
npm audit --audit-level=moderate
npm run typecheck
npm run build:docker
```

Results:
- npm install: passed.
- npm audit: 0 vulnerabilities.
- TypeScript typecheck: passed.
- Vite production build: passed.

Targeted tests:

```bash
npx vitest run \
  src/lib/fieldObjectiveEngine.test.ts \
  src/lib/fieldActionLifecycle.test.ts \
  src/lib/fieldViewGovernance.test.ts \
  src/lib/fieldViewDecisionScript.test.ts \
  src/lib/fieldViewActionDeck.test.ts \
  src/lib/designSystemGovernance.test.ts \
  src/lib/runtimeEndpointGovernance.test.ts \
  src/lib/fieldHealthReport.test.ts \
  src/lib/fieldFarmerMetrics.test.ts \
  src/lib/fieldZoneVra.test.ts \
  --no-file-parallelism --maxWorkers=1
```

The long combined run timed out at the shell limit after 8/10 files had already passed. The two remaining files were then rerun separately and passed.

Confirmed targeted total:
- 10 test files passed.
- 42 tests passed.

Field segmentation service tests:

```bash
cd services/field-segmentation
python -m pytest -q test_exg_preprocess.py test_segmentation.py
```

Result:
- 29 passed.

## Honest caveat
This is source/build/targeted-test verification. It is not a full Docker Compose runtime test and not a full browser E2E test.
