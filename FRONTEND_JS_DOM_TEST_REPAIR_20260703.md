# Frontend JS DOM Test Repair — 2026-07-03

## Scope
Repaired the remaining frontend test/runtime issues found after hardening the frontend container and adding the two-year imagery timeline thumbnails.

## Changes Applied

### 1. AddFieldWithMap accessibility + test determinism
- Added unique Arabic `aria-label` values for duplicate Undo/Redo buttons:
  - `تراجع من لوحة النموذج`
  - `إعادة من لوحة النموذج`
  - `تراجع من الخريطة`
  - `إعادة من الخريطة`
- This fixes ambiguous accessible-name collisions where two visible buttons were both named `تراجع` / `إعادة`.
- Updated `AddFieldWithMap.undoredo.test.tsx` to:
  - wrap synthetic draw events in React `act(...)`;
  - target the form-panel Undo/Redo controls explicitly.

### 2. AddFieldWithMap workspace jsdom mocks
- Updated `AddFieldWithMap.workspace.test.tsx` mocks to match the current component surface:
  - `useMap().on/off/getContainer` for draw-start listeners;
  - `L.divIcon` and `L.marker` for center/radius handle initialization.
- Updated the stale pivot-control assertion to match the current UI: `دائرة (مركز + نصف قطر)` + radius input placeholder.

### 3. FieldIndicatorMap static contract
- Updated the static guard to reflect the real cache-aware tile URL call:
  - `fieldIndicatorTileUrl(fieldId, normalizedIndex, date, tenantId, tileCacheVersion)`

### 4. FieldWorkspaceMapCard available-dates side-effect
- Updated tests to mock the new `/available-dates` request deterministically with an empty dates payload.
- This prevents jsdom tests from failing on the new timeline-date lookup side effect.

## Verification Performed

```bash
cd frontend
npm run typecheck
npm run build:docker
npx vitest run src/components/AddFieldWithMap.undoredo.test.tsx --reporter=verbose
npx vitest run src/components/AddFieldWithMap.workspace.test.tsx --reporter=verbose
npx vitest run src/components/FieldIndicatorMap.static.test.ts --reporter=verbose
npx vitest run src/sections/FieldWorkspaceMapCard.test.tsx --reporter=verbose
```

## Results

- TypeScript typecheck: PASS
- Vite production build: PASS
- AddFieldWithMap undo/redo tests: 3 passed
- AddFieldWithMap workspace tests: 4 passed
- FieldIndicatorMap static tests: 4 passed
- FieldWorkspaceMapCard tests: 9 passed

## Note
The full monolithic `npm run test:ci` runner can still be slow/hang in this constrained container when many jsdom suites are run in one Vitest process. The repaired failing suites now pass individually, which is the safer mode already supported by the project smart-runner pattern.
