# SAHOOL Frontend Container Hardening — 2026-07-03

## Scope
Inspected the web frontend container (`frontend/Dockerfile`, `frontend/nginx.conf`, `docker-compose.v9.yml`, `docker-compose.v9.gpu.yml`, `docker-compose.fixed.yml`) after the ExG/SAM2 and two-year imagery timeline changes.

## Fixes applied

1. **Vite build-time environment is now explicit**
   - `frontend/Dockerfile` now declares and exports:
     - `VITE_API_MODE`
     - `VITE_MOCK_MODE`
     - `VITE_API_URL`
     - `VITE_WS_URL`
     - `VITE_DEV_PROXY_TARGET`
   - This closes the previous mismatch where compose passed `VITE_API_URL`/`VITE_WS_URL`, but the Dockerfile did not expose them to the Vite build environment.

2. **Compose build args aligned**
   - Updated frontend build args in:
     - `docker-compose.v9.yml`
     - `docker-compose.v9.gpu.yml`
     - `docker-compose.fixed.yml`
   - Added `VITE_API_MODE=${VITE_API_MODE:-gateway}` and `VITE_MOCK_MODE=${VITE_MOCK_MODE:-false}`.

3. **MapHub TypeScript production build fix**
   - Fixed a strict TypeScript error in `frontend/src/sections/MapHub.tsx` where `selected` could be undefined inside the two-year imagery thumbnail timeline renderer.
   - The timeline thumbnail URL now safely uses optional access for the selected field.

4. **Drawing bundle split/test-safety improvement**
   - Removed the static re-export of `LeafletDrawAdapter` from `src/components/maphub/drawing/index.ts`.
   - This prevents a side-effect import of `leaflet-draw` when consumers only need validation/types from the drawing core.
   - It also removes the Vite warning where `LeafletDrawAdapter` was both statically and dynamically imported.

5. **Nginx frontend container hardening**
   - Added `server_tokens off`.
   - Added no-store caching for `index.html` so browsers do not keep a stale SPA shell after deployments.
   - Changed asset `Cache-Control` to `always`.
   - Hardened security headers with `always` and added:
     - `Permissions-Policy`
     - `Cross-Origin-Opener-Policy`
     - `Cross-Origin-Resource-Policy`
   - Kept `/api/raster/` as `^~` so raster PNG tile requests do not fall into the static PNG regex cache block.

## Verification performed

Inside `frontend/`:

```bash
npm ci --legacy-peer-deps --ignore-scripts
npm run typecheck
npm run build:docker
```

Results:

- `npm ci`: passed, 0 vulnerabilities reported by npm audit.
- `npm run typecheck`: passed.
- `npm run build:docker`: passed.

## Test status note

`npm run test:ci` was attempted after dependency installation. It did not complete fully in the available execution window and exposed pre-existing jsdom/front-end test issues unrelated to the container runtime build:

- `AddFieldWithMap.undoredo.test.tsx`: stale jsdom mocks around Leaflet map/drawing interactions.
- `FieldWorkspaceMapCard.test.tsx`: UI assertions need updating after recent component rendering changes.

These do not block the production frontend container build, but they should be repaired in a focused test-maintenance pass.
