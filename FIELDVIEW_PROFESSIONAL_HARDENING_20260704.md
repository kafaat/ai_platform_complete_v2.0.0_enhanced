# FIELDVIEW PROFESSIONAL HARDENING — 2026-07-04

## Scope
This pass hardens the user data flow around the FieldView pattern. The objective is to make the active field a resilient, explainable, and shareable source of truth across the frontend rather than a set of independent local selections.

## Implemented changes

### 1. FieldView store provenance
Updated `frontend/src/hooks/useFieldContext.ts`:

- Added `selectionSource`: `user | route | auto | restore | system`.
- Added `selectedAt` timestamp.
- Added `selectedFieldName` for human-readable recovery and UI transparency.
- Added `clearSelectedField()`.
- Kept backward compatibility: `setSelectedField(id)` still works, while `setSelectedField(id, meta)` records richer intent.
- Persisted only safe session-scoped context in `sessionStorage`.

### 2. Pure FieldView resolver
Updated `frontend/src/lib/fields.ts`:

- Added `resolveFieldViewSelection()`.
- Added `isKnownFieldId()`.
- Added `readFieldIdFromSearch()` and `writeFieldIdToSearch()`.
- Resolver priority is now explicit and testable:
  1. valid deep-link route field,
  2. valid session-stored field,
  3. first available field fallback,
  4. honest empty state.
- Invalid route/stored ids are surfaced instead of silently hiding drift.

### 3. Professional `useSelectedField`
Updated `frontend/src/hooks/useSelectedField.ts`:

- Accepts optional `routeFieldId`.
- Returns richer state:
  - `selectionReason`,
  - `routeFieldIsInvalid`,
  - `storedFieldIsInvalid`,
  - `selectionSource`,
  - `selectedAt`,
  - `hasFields`,
  - `isEmpty`,
  - `clearFieldId`.
- Auto-heals stale stored field ids when a field is deleted or tenant context changes.
- Deep links now converge through the same hook instead of bespoke per-screen effects.

### 4. MapHub FieldView deep-link hardening
Updated `frontend/src/sections/MapHub.tsx`:

- Passes `routeFieldId` directly into `useSelectedField({ routeFieldId })`.
- Removed the duplicate local route synchronization effect.
- Added a FieldView status banner when:
  - the deep-link field id is invalid,
  - the stored field id is stale,
  - the screen was opened from a valid FieldView deep link.
- This improves operator trust and avoids silent fallback confusion.

### 5. MyFields source metadata
Updated `frontend/src/sections/MyFieldsPage.tsx`:

- Field open action now stores both id and name with `source: 'user'`.
- Keyboard activation path now uses the same metadata as mouse click.

### 6. Chatbot FieldView integration
Updated `frontend/src/sections/ChatbotPage.tsx`:

- Removed direct FieldView store reading.
- Uses `useSelectedField()` so chat follows the same active field as the rest of FieldView.
- AI runtime request now includes active field name in `current_field_state` alongside `field_id`.

### 7. Static guards and unit tests
Updated/added tests:

- `frontend/src/hooks/useSelectedField.static.test.ts`
  - prevents sections from reintroducing local `useFieldOptions` selection,
  - prevents direct `useFieldContext` reads except documented entry/sync points.
- `frontend/src/lib/fields.fieldview.test.ts`
  - covers route priority,
  - invalid route fallback,
  - stale stored id fallback,
  - empty state,
  - query normalization.

## Verification

Executed in `frontend/`:

```bash
npm ci --legacy-peer-deps --ignore-scripts
npm run typecheck
npm run build:docker
npx vitest run src/lib/fields.fieldview.test.ts src/hooks/useSelectedField.static.test.ts --no-file-parallelism --maxWorkers=1
npx vitest run src/sections/MapHubTwoYearBackfill.static.test.ts src/sections/MapHubTwoYearTimeline.static.test.ts src/sections/MapHubSatelliteDefault.static.test.ts src/sections/MyFieldsPage.num.test.ts src/sections/ChatbotPage.endpoint.test.ts --no-file-parallelism --maxWorkers=1
```

Results:

- `npm ci`: passed, `0 vulnerabilities`.
- `typecheck`: passed.
- `build:docker`: passed.
- FieldView tests: 2 files passed, 7 tests passed.
- Regression/static UI tests: 5 files passed, 17 tests passed.

## Final state
FieldView is now not just present; it is hardened as a traceable frontend data-flow contract:

`MyFields → FieldView store → MapHub/Satellite/Workspace/Recommendations/Chatbot/Operations → AI/context/reports`

The active field is shareable via URL, recoverable after stale state, visible to users when fallback happens, and guarded against regression by static tests.
