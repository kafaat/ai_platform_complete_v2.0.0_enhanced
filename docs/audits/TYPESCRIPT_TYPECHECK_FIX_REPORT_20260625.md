# TypeScript Typecheck Fix Report — 2026-06-25

## Issue
`npm run typecheck` failed because the new `lab-sampling` route was present in `PageId` but absent from the frontend RBAC registry in `src/lib/permissions.ts`.

## Root Cause
The page completeness guard is intentionally fail-closed. It detected that `lab-sampling` was routable but not explicitly assigned to any role/page matrix.

## Fix
Added `lab-sampling` to:

- `ALL_PAGES`
- `WORKER_PAGES`

This keeps the page governed by explicit RBAC instead of being accidentally hidden or bypassing frontend policy.

## Verification

- `npm run typecheck`: PASS
- `npm run build`: PASS

## Notes
Backend endpoint authorization remains unchanged and still relies on `FIELD_VIEW` / `FIELD_EDIT` for lab endpoints.
