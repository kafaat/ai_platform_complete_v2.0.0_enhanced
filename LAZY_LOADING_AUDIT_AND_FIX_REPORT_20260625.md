# SAHOOL Lazy Loading Audit & Fix — 2026-06-25

## Scope
Checked the latest `service_ui_connected` package for lazy/progressive loading in:
- React web routes, components, images, large lists, maps, raster/weather layers.
- Flutter/mobile list rendering patterns.
- Map tile/overlay loading patterns.

## Findings

### Web route/component lazy loading
- `frontend/src/App.tsx` uses `lazy(() => import(...))` extensively for application pages.
- `Suspense` is present around page rendering.
- `MapHub` lazily loads heavy map engines/components:
  - `HubMapGL`
  - `TerrainView3D`
- `SQLWorkspacePage` lazily loads the DuckDB/WASM SQL editor.

Status: PASS.

### Web image lazy loading
Before this fix:
- Actual runtime `<img>` tags were found in:
  - `frontend/src/sections/TasksPage.tsx`
  - `frontend/src/components/shell/ContextBar.tsx`
- Neither used `loading="lazy"` or `decoding="async"`.

Applied fix:
- Added `loading="lazy" decoding="async"` to task documentation photos.
- Added `loading="lazy" decoding="async"` to tenant logo image.

Status after fix: PASS for real runtime `<img>` tags.

Note: `frontend/src/sections/ChatbotPage.tsx` contains the string `<img onerror>` only inside a security comment about XSS sanitization; it is not a rendered image element.

### Map/satellite/weather loading
- Raster/agronomic layers use map tile patterns (`TileLayer`, MapLibre raster sources, tile URLs).
- Tiles load progressively by viewport/zoom rather than loading full scenes at once.
- Weather/wind overlay is implemented as overlay/canvas/SVG style rendering above the unified map, not as full-page image loading.

Status: PASS.

### Long lists / virtualization
- Alert list uses `react-window` / `FixedSizeList` for long lists.
- Flutter/mobile code uses `ListView.builder` and `GridView.builder` patterns.

Status: PARTIAL PASS.
Recommendation: apply virtualization/builder patterns to every long operational feed: daily logs, task history, notifications, equipment events, sensor readings.

### Flutter/mobile images
- No `Image.network`, `CachedNetworkImage`, or `FadeInImage` occurrences were found in the checked Dart files.
- Since no network image rendering was found, no image lazy-loading issue was detected there.
- Mobile list loading uses builder patterns, but explicit `cacheExtent` tuning was not found.

Status: ACCEPTABLE, with future improvement recommended if network images are added.

## Validation
- `npm ci`: PASS
- `npm run typecheck`: PASS
- `npm run build`: PASS

## Changed files
- `frontend/src/sections/TasksPage.tsx`
- `frontend/src/components/shell/ContextBar.tsx`
- `LAZY_LOADING_AUDIT_AND_FIX_REPORT_20260625.md`

## Production recommendations
1. Enforce lint rule/check for all `<img>` tags to include `loading="lazy"` unless explicitly marked as above-the-fold.
2. Use priority/eager loading only for critical logo/hero assets visible at first paint.
3. Keep satellite, weather, and indicator layers as tiled/viewport-driven sources.
4. Add virtualized/builder rendering to daily logs and sensor/equipment history if they can exceed 100 rows.
5. Use `CachedNetworkImage` or equivalent if mobile starts rendering remote task/scouting/equipment photos.
