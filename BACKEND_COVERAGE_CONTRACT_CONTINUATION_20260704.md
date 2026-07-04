# SAHOOL — Backend Coverage Contract Continuation

Date: 2026-07-04
Base: `sahool_main_5015796_backend_coverage_contract_final.zip`
Output: `sahool_main_5015796_backend_coverage_contract_continued_final.zip`

## Scope

Continued the backend-to-frontend exposure hardening by closing the remaining P1 gap in the coverage registry:

- Crop planning
- Planting windows
- Rotation advice
- Crop operations calendar
- GDD stage tracking

The previous registry kept `crop-planning-rotation-planting` as `partial` because GDD tracking and operations-calendar were not represented as Field Objective targets. This patch promotes that layer to `covered` with explicit hooks and objective targets.

## Changes

### 1. Field Objective Engine extended

Updated:

- `frontend/src/lib/fieldObjectiveEngine.ts`
- `frontend/src/components/fieldview/FieldObjectivePanel.tsx`
- `frontend/src/sections/MapHub.tsx`

Added objective IDs:

- `check_planting_window`
- `plan_rotation`
- `track_gdd_stage`

Added evidence sources:

- `planning`
- `gdd`

MapHub now calculates these evidence flags from live context:

- `planning`: crop context exists
- `gdd`: crop + current weather + season/phenology context exist

No optimistic evidence is invented.

### 2. Backend hooks added

Updated:

- `frontend/src/hooks/useApi.ts`

Added:

- `useCropOperationsCalendar`
- `useGddTrack`

Mapped endpoints:

- `GET /api/v1/crops/{crop_id}/operations-calendar`
- `POST /api/v1/gdd/track`

GDD remains honest: it requires an explicit temperature series; the frontend does not synthesize one.

### 3. Planting Advisor enhanced

Updated:

- `frontend/src/components/fieldview/PlantingAdvisorCard.tsx`

It now reads the crop operations calendar and shows whether stage-operation guidance exists for the current or selected crop.

### 4. Coverage registry promoted

Updated:

- `frontend/src/config/backendCoverageRegistry.ts`
- `frontend/src/config/backendCoverageRegistry.test.ts`

Layer changed:

- `crop-planning-rotation-planting`: `partial` → `covered`

Hooks now registered:

- `usePlantingCheck`
- `useRotationSuggest`
- `useCropOperationsCalendar`
- `useGddTrack`

Surfaces now registered:

- `PlantingAdvisorCard`
- `FieldObjectivePanel`

Coverage summary changed:

```text
covered: 12
partial: 4
waived_internal: 1
not_ready: 1
```

Critical P0/P1 gaps are now empty in the registry.

## Verification performed

Frontend:

```bash
npm ci --legacy-peer-deps --ignore-scripts
npm audit --audit-level=moderate
npx vitest run src/config/backendCoverageRegistry.test.ts src/config/endpoints.test.ts src/lib/fieldObjectiveEngine.test.ts src/lib/fieldObjectiveHiddenGaps.test.ts src/lib/fieldObjectiveDeeperGaps2.test.ts src/lib/fieldActionLifecycle.test.ts --no-file-parallelism --maxWorkers=1
npm run typecheck
npm run build:docker
```

Results:

- npm ci: passed
- npm audit: 0 vulnerabilities
- targeted frontend tests: 6 files / 44 tests passed
- typecheck: passed
- build:docker: passed

Field segmentation:

```bash
cd services/field-segmentation && pytest -q
```

Result:

- 29 passed

## Honest limitation

This is source/static/build verification plus targeted tests. It is not a full Docker Compose runtime verification and not a full Playwright browser E2E run.
