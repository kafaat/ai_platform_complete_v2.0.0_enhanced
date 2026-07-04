# Final Green Merge — Frontend + Backfill + ExG/SAM2

Date: 2026-07-03

## Source
Merged the user-provided `sahool_main_2987c5e_timeline_backfill_thumbnails_green.zip` with the latest repaired frontend/container/test fixes from the previous Sahool working branch.

## Preserved from the green upload
- Timeline backfill thumbnails integration.
- Platform proxy path for historical imagery backfill.
- ExG-assisted SAM2 boundary flow.
- ExG user-facing transparency in `AddFieldWithMap`:
  - shows ExG preprocessing notice.
  - warns when vegetation confidence is low.
- Event-bus entry for `FIELD_IMAGERY_BACKFILL_REQUESTED`.
- Safer MapHub thumbnail rendering guarded by `selected`.

## Merged improvements
- Frontend Docker build arguments exposed to Vite:
  - `VITE_API_MODE`
  - `VITE_MOCK_MODE`
  - `VITE_API_URL`
  - `VITE_WS_URL`
  - `VITE_DEV_PROXY_TARGET`
- `docker-compose.v9.yml` now passes frontend build args explicitly.
- Frontend nginx hardening:
  - `server_tokens off`
  - no-store for `index.html`
  - immutable caching for static assets with `always`
  - security headers with `always`
  - `Permissions-Policy`
  - `Cross-Origin-Opener-Policy`
  - `Cross-Origin-Resource-Policy`
- Drawing bundle hardening:
  - removed static export of LeafletDrawAdapter from the drawing barrel to avoid side-effect loading.
- JS DOM test repairs:
  - disambiguated undo/redo buttons with aria-labels.
  - updated Leaflet mocks.
  - updated FieldIndicator tile cache contract test.
  - mocked available-dates request in FieldWorkspaceMapCard tests.

## Verification run

### Backend segmentation
```bash
cd services/field-segmentation
python -m pytest -q
```
Result:
```text
29 passed in 3.35s
```

### Frontend dependencies
```bash
cd frontend
npm ci --legacy-peer-deps --ignore-scripts
```
Result:
```text
added 441 packages
found 0 vulnerabilities
```

### Frontend build
```bash
npm run build:docker
```
Result:
```text
vite build succeeded
```

### Targeted frontend tests
```bash
npx vitest run \
  src/components/AddFieldWithMap.undoredo.test.tsx \
  src/components/AddFieldWithMap.workspace.test.tsx \
  src/components/FieldIndicatorMap.static.test.ts \
  src/sections/FieldWorkspaceMapCard.test.tsx \
  --no-file-parallelism --maxWorkers=1
```
Result:
```text
4 test files passed
20 tests passed
```

## Note
`tsc --noEmit` was attempted separately, but it did not complete within a 240s local timeout in this environment. The production Vite Docker build completed successfully.
