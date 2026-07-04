# DEEPER_HIDDEN_GAPS_HARDENING_20260704

## Scope
Second-pass forensic hardening on top of `sahool_main_777582b_field_objective_engine_hidden_gaps_final.zip`, focused on hidden Field Objective Engine and FieldView evidence/lifecycle gaps.

## Closed gaps

### 1. Task lifecycle accepted missing task backend
`FieldObjectivePanel` previously allowed lifecycle advancement when `onCreateTask` was absent or returned `undefined`. That could mark a task as created even when no real backend/task route accepted it.

Fix:
- `onCreateTask` now must return `true` explicitly.
- Async `Promise<boolean>` is supported.
- Missing callback, `false`, `undefined`, or thrown error does not advance lifecycle.

Files:
- `frontend/src/components/fieldview/FieldObjectivePanel.tsx`
- `frontend/src/lib/fieldObjectiveHiddenGaps.test.ts`

### 2. Malformed day follow-up could leak as `{ days: undefined }`
`followUpForObjective()` could be called directly with a malformed day-based objective and return an invalid cadence.

Fix:
- `followUpForObjective()` validates `followUpDays` as finite positive number.
- Invalid day cadence returns `{ kind: 'none' }`.
- `advanceLifecycle(..., 'schedule_follow_up')` also blocks objectives with `followUp='none'` and invalid day cadence.

Files:
- `frontend/src/lib/fieldActionLifecycle.ts`
- `frontend/src/lib/fieldObjectiveHiddenGaps.test.ts`

### 3. Season profitability could treat metadata as real records
`MapHub` previously treated crop/area metadata as records evidence. This could unlock `review_season_profitability` without real completed operations or water-efficiency evidence.

Fix:
- `records` evidence now requires `completedOps.length > 0` or `waterEfficiencyQ.data`.
- Crop/area alone no longer count as operational records.

Files:
- `frontend/src/sections/MapHub.tsx`
- `frontend/src/lib/fieldObjectiveHiddenGaps.test.ts`

### 4. Zone evidence meaning clarified
`zones` evidence now represents either existing saved zones or readiness to build zones from ready imagery.

Fix:
- `zones: zonePersisted.length > 0 || imageryReadyCount > 0`
- This keeps VRA workflow unblocked when imagery can generate zones, while preferring actual saved zones when present.

File:
- `frontend/src/sections/MapHub.tsx`

## Verification actually run

Frontend:

```bash
npm ci --legacy-peer-deps --ignore-scripts
npm audit --audit-level=moderate
npm run typecheck
npm run build:docker
npx vitest run \
  src/lib/fieldActionLifecycle.test.ts \
  src/lib/fieldObjectiveEngine.test.ts \
  src/lib/fieldObjectiveHiddenGaps.test.ts \
  src/lib/fieldHealthReport.test.ts \
  src/lib/fieldFarmerMetrics.test.ts \
  src/lib/fieldZoneVra.test.ts \
  src/lib/fieldEconomics.test.ts \
  src/lib/fieldViewGovernance.test.ts \
  src/lib/fieldViewActionDeck.test.ts \
  src/lib/fieldViewDecisionScript.test.ts \
  src/lib/designSystemGovernance.test.ts \
  src/lib/runtimeEndpointGovernance.test.ts \
  src/hooks/fieldViewUiWide.static.test.ts \
  --no-file-parallelism --maxWorkers=1
```

Result:
- `npm ci`: passed
- `npm audit`: 0 vulnerabilities
- `typecheck`: passed
- `build:docker`: passed
- targeted FieldView/Objective/P0-P4 tests: 13 files passed / 59 tests passed

Backend targeted:

```bash
python -m pytest -q tests/security/test_phase4_security_observability_contracts.py
```

Result:
- 6 passed

Segmentation:

```bash
cd services/field-segmentation && python -m pytest -q
```

Result:
- 29 passed

## Honest caveat
This is source/build/targeted-test verification. It is not a full Docker Compose runtime, not a full browser E2E pass, and not a production deployment certification.
