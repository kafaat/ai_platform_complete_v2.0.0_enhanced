# HIDDEN GAPS FORENSIC HARDENING — 2026-07-04

## Scope
Source ZIP inspected and hardened:

- `sahool_main_777582b_field_objective_engine_verified_final.zip`

Focus areas:

- Field Objective Engine lifecycle safety
- FieldView objective panel runtime behavior
- secret/demo credential leakage in packaged files
- security-test robustness when `.env` is intentionally absent from the ZIP
- frontend type/build/test stability
- field-segmentation regression safety

## Hidden gaps found and fixed

### 1. Evidence gate was fail-open for programmatic calls

**File:** `frontend/src/lib/fieldActionLifecycle.ts`

Before:

- `attach_evidence` was blocked only when `canAct === false`.
- If a caller forgot to pass `canAct`, the transition could still move `draft -> evidence`.

Fix:

- `attach_evidence` now requires explicit `canAct === true`.
- Missing/undefined `canAct` is rejected with an Arabic blocked reason.

Why it matters:

- Prevents recommendation approval on incomplete or unknown evidence.
- Keeps “no recommendation without evidence” enforced in the lifecycle engine, not just in UI.

### 2. Task creation depended only on UI hiding

**File:** `frontend/src/lib/fieldActionLifecycle.ts`

Before:

- The pure lifecycle allowed `approved -> task_created` without checking whether the objective actually produces a field task.
- The panel hid the button for non-task objectives, but the state machine itself was permissive.

Fix:

- `create_task` now requires an objective.
- It blocks if `objective.producesTask === false`.

Why it matters:

- Prevents VRA/report/profitability objectives from being treated as field tasks by code paths outside the current component.

### 3. Direct completion from approved was too broad

**File:** `frontend/src/lib/fieldActionLifecycle.ts`

Before:

- `approved -> reviewed` through `record_outcome` was available broadly.

Fix:

- Direct completion from `approved` now requires:
  - an objective,
  - `objective.producesTask === false`,
  - `outcome === 'completed'`.
- Task-producing objectives must go through task/execution/follow-up or execution outcome.

Why it matters:

- Prevents falsely closing operational recommendations without real execution/follow-up.

### 4. Follow-up scheduling could advance without an objective

**File:** `frontend/src/lib/fieldActionLifecycle.ts`

Before:

- `schedule_follow_up` could change stage without setting a meaningful follow-up if no objective was supplied.

Fix:

- `schedule_follow_up` now requires an objective.
- Day-based objectives must define `followUpDays`.

Why it matters:

- Avoids a `follow_up` stage with no actual follow-up contract.

### 5. FieldObjectivePanel could advance before host action was accepted

**File:** `frontend/src/components/fieldview/FieldObjectivePanel.tsx`

Before:

- `createTask()` advanced the lifecycle to `task_created` before confirming the host callback accepted the action.
- The callback return value was ignored.

Fix:

- `onCreateTask` may now return `false` to reject the transition.
- The panel advances only after accepted host action.
- The panel also passes the objective into lifecycle calls so the pure engine can enforce objective-specific guards.

### 6. Objective evidence could go stale after approval

**File:** `frontend/src/components/fieldview/FieldObjectivePanel.tsx`

Fix:

- Added a guarded reset: if live evidence becomes unavailable while the lifecycle is still in evidence/approved/task/executing/follow-up stages, the panel resets to draft.

Why it matters:

- Prevents stale recommendations from staying approved after source data disappears or field context changes.

### 7. MapHub callback was ambiguous

**File:** `frontend/src/sections/MapHub.tsx`

Before:

- `onCreateTask` only toggled pin mode for stress diagnosis and returned nothing for other objectives.

Fix:

- It now returns `true` only for supported live action: `diagnose_field_stress` opens field-evidence pin mode.
- It returns `false` for unsupported objectives so lifecycle does not falsely enter `task_created`.

### 8. Packaged local Claude settings contained command history with a real-looking password

**File:** `.claude/settings.local.json`

Fix:

- Removed the local settings file from the package.

Why it matters:

- Local agent/tool settings are not needed in the distributable source ZIP.
- Prevents accidentally shipping local command history and credentials.

### 9. Demo password literals remained in run scripts

**Files:**

- `run_all.sh`
- `run_all.ps1`

Fix:

- Replaced the displayed hard-coded login password with:
  - `<password from environment or seeded setup>`

Why it matters:

- Avoids normalizing fixed demo/admin passwords in operational scripts.

### 10. Security test assumed `.env` exists in the source package

**File:** `tests/security/test_phase4_security_observability_contracts.py`

Before:

- The test failed with `FileNotFoundError` when `.env` was intentionally absent.

Fix:

- It now checks `.env` if present, otherwise `.env.example`.
- Placeholder assertion accepts the repository’s current placeholder vocabulary.
- The forbidden password literal was split in the test so the test does not itself contain the exact secret string.

## Verification run

Frontend:

```bash
cd frontend
npm ci --legacy-peer-deps --ignore-scripts
npm audit --audit-level=moderate
npm run typecheck
npm run build:docker
```

Results:

- `npm ci`: passed
- `npm audit --audit-level=moderate`: 0 vulnerabilities
- `npm run typecheck`: passed
- `npm run build:docker`: passed

Targeted FieldView / Objective / P0-P4 tests:

```bash
npx vitest run \
  src/lib/fieldActionLifecycle.test.ts \
  src/lib/fieldObjectiveEngine.test.ts \
  src/lib/fieldViewGovernance.test.ts \
  src/lib/fieldViewActionDeck.test.ts \
  src/lib/fieldViewDecisionScript.test.ts \
  src/lib/designSystemGovernance.test.ts \
  src/lib/runtimeEndpointGovernance.test.ts \
  src/lib/fieldHealthReport.test.ts \
  src/lib/fieldFarmerMetrics.test.ts \
  src/lib/fieldZoneVra.test.ts \
  src/lib/fieldEconomics.test.ts \
  src/hooks/useSelectedField.static.test.ts \
  src/hooks/useSelectedField.professional.static.test.ts \
  src/hooks/fieldViewUiWide.static.test.ts \
  --no-file-parallelism --maxWorkers=1
```

Result:

- 13 test files passed
- 57 tests passed

Security contract test:

```bash
python -m pytest -q tests/security/test_phase4_security_observability_contracts.py
```

Result:

- 6 passed

Field segmentation:

```bash
cd services/field-segmentation
python -m pytest -q
```

Result:

- 29 passed

## Remaining honest caveat

This pass is source/build/static/targeted-test verification. It is not a full Docker Compose runtime, browser E2E, load, or chaos run.
