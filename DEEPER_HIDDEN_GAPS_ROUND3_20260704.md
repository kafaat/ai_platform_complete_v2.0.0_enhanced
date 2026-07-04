# DEEPER HIDDEN GAPS — ROUND 3 (2026-07-04)

Base: `sahool_main_777582b_field_objective_engine_deeper_hidden_gaps_final.zip`

Scope: Field Objective Engine, recommendation lifecycle, FieldView context binding, task-creation honesty, static security scan, targeted frontend/backend tests.

## Closed gaps

### 1. Lifecycle could be carried across fields
`FieldObjectivePanel` was mounted inside `MapHub` without a context key. If the active field changed while the panel stayed mounted, an approved/in-progress objective lifecycle could remain visible for the new field.

Fix:
- Added `contextKey?: string | null` to `FieldObjectivePanel`.
- `MapHub` now passes `contextKey={fieldId}`.
- The panel resets lifecycle, blocked message, and task-creation busy state when context changes.

### 2. Task creation failure was silent
Previous guard correctly required `onCreateTask` to return `true`, but failures were invisible to the user. Unsupported objectives such as irrigation/spray task creation in this screen could no-op silently.

Fix:
- Added `blockedMessage` state and visible `role="status"` warning.
- Missing callback, `false`, thrown errors, or unsupported objective now show a reason and do not advance lifecycle.

### 3. Double-click could request duplicate task creation
`createTask` had no busy/idempotency guard. A fast double click could call the host task creation path twice before lifecycle state changed.

Fix:
- Added `creatingTask` guard.
- Disabled the task button while awaiting `onCreateTask`.
- Added explicit pending label.

### 4. Field outcomes could bypass scheduled follow-up
The lifecycle allowed `executing → reviewed` directly even for objectives that require `next_image` or `days` follow-up. That weakened the purpose of the review loop.

Fix:
- Task-producing objectives with follow-up must pass through `schedule_follow_up` before `record_outcome`.
- Direct outcome from `executing` is blocked for follow-up objectives.

### 5. Unknown or completed outcomes could be recorded incorrectly
`record_outcome` could default to `unknown`; task objectives could also be closed with `completed`, which is not a field-impact outcome.

Fix:
- `record_outcome` now requires an explicit non-unknown outcome.
- Task-producing objectives only accept real field outcomes: `improved`, `stable`, `declined`.
- Non-field deliverables still close as `completed` from `approved`.

## Added tests

- `frontend/src/lib/fieldObjectiveDeeperGaps2.test.ts`
- Updated `fieldActionLifecycle.test.ts`
- Updated `fieldObjectiveHiddenGaps.test.ts`

Coverage added for:
- no lifecycle carryover across `fieldId`
- no silent task creation failure
- no duplicate task creation while pending
- no direct outcome before scheduled follow-up
- no unknown outcome as reviewed
- no `completed` as a task field-impact outcome

## Verification run

Frontend:

```bash
cd frontend
npm ci --legacy-peer-deps --ignore-scripts
npm audit --audit-level=moderate
npm run typecheck
npm run build:docker
npx vitest run src/lib/fieldObjective*.test.ts src/lib/fieldActionLifecycle.test.ts src/lib/fieldHealthReport.test.ts src/lib/fieldFarmerMetrics.test.ts src/lib/fieldZoneVra.test.ts src/lib/fieldEconomics.test.ts src/lib/fieldView*.test.ts src/lib/fields.fieldview.test.ts --no-file-parallelism --maxWorkers=1
```

Results:
- `npm ci`: passed
- `npm audit`: 0 vulnerabilities
- `typecheck`: passed
- `build:docker`: passed
- targeted frontend tests: 12 files / 64 tests passed

Backend/security:

```bash
python -m pytest tests/security/test_phase4_security_observability_contracts.py -q
cd services/field-segmentation && python -m pytest -q
```

Results:
- security contract tests: 6 passed
- field-segmentation: 29 passed

## Notes

This is source/build/targeted-test verification. It is not a full Docker Compose runtime test and not a Playwright browser E2E run.

Static scans still show test-only placeholder tokens and documentation examples. No production `.claude/settings.local.json` was included.
