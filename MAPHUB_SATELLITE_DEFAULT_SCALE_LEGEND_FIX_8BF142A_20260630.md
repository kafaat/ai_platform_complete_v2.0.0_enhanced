# MapHub Satellite Default + Scale Legend Fix — rc.16_8bf142a

## Problem
The latest rc.16_8bf142a package still allowed MapHub to open with the weather overlay from persisted workspace state, and the indicator scale legend could be absent because the active indicator default was `null` unless explicitly routed.

## Fixes

### 1) Satellite/indicator view is now the default
Updated `frontend/src/sections/MapHub.tsx`:
- `activeIndicator` now defaults to `ndvi` when opening MapHub.
- `requestedCdseOpen` still honors explicit route indicator overrides.
- Choosing `بلا` remains possible manually via the layer selector.

### 2) Weather is no longer restored as the default overlay
Updated `frontend/src/sections/MapHub.tsx`:
- `showWeather` now initializes only from explicit `weather=1`, `weather=true`, or `routeState.showWeather === true`.
- Persisted workspace weather state is no longer allowed to make weather the default screen.

### 3) MyFields opens MapHub with NDVI and weather disabled
Updated `frontend/src/sections/MyFieldsPage.tsx`:
- Adds `indicator: 'ndvi'`.
- Adds `showWeather: false`.

### 4) Persistent scale legend in toolbar
Updated `frontend/src/sections/MapHub.tsx`:
- Adds `activeIndicatorLegend` and `activeIndicatorCmap`.
- Renders `ColormapLegend` inside the toolbar with `data-testid="indicator-scale-legend"`.

## Validation
Executed:
- `npm test -- src/sections/MapHubSatelliteDefault.static.test.ts src/sections/MapHubTwoYearBackfill.static.test.ts src/sections/MapHubTwoYearTimeline.static.test.ts`
- `npm run typecheck`
- `npm run build`
- `python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core`

Results:
- 3 frontend test files passed
- 9 frontend tests passed
- TypeScript typecheck passed
- Vite production build passed
- Backend compile guard passed
