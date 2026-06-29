# SAHOOL Weather Engine v27 — User Preferences Persistence

## Scope

This phase continues from `sahool_v26.zip` and adds persistent user preferences for the MapHub Weather overlay.

## Implemented

### 1. Weather overlay preferences module

Added:

```text
frontend/src/components/maphub/weather/weatherPreferences.ts
```

The module provides:

- `defaultWeatherPreferences()`
- `readWeatherPreferences()`
- `writeWeatherPreferences()`
- `resetWeatherPreferences()`
- `WEATHER_PREFERENCES_STORAGE_KEY`

Storage key:

```text
sahool.weather.overlay.preferences.v1
```

Persisted values:

- selected weather layer
- selected forecast time
- selected weather model
- overlay opacity
- wind animation enabled/disabled
- wind density
- panel open/collapsed state

### 2. Safe browser/runtime behavior

The implementation guards all browser-only APIs:

- `typeof window !== 'undefined'`
- `window.localStorage`
- `window.matchMedia`
- `window.innerWidth`

This avoids breaking server-side rendering, static analysis, or test environments.

### 3. Validation and coercion

Loaded preferences are validated against current definitions:

- `WEATHER_LAYERS`
- `WEATHER_TIMES`
- `WEATHER_MODELS`
- `WIND_DENSITIES`

Invalid or stale values fall back safely to defaults.

Opacity is clamped to a safe UI range.

### 4. WeatherRasterOverlay integration

Updated:

```text
frontend/src/components/maphub/weather/WeatherRasterOverlay.tsx
```

The overlay now:

- reads saved preferences on first render
- uses saved values as initial state
- writes updated preferences whenever the user changes layer/time/model/opacity/wind density/panel state

### 5. Static contract test

Updated:

```text
frontend/src/components/maphub/weather/WeatherEngine.static.test.ts
```

The test now verifies the preferences module and storage contract.

## Verification

### Backend

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
```

Weather test suite executed:

```text
43 passed
```

### Frontend

```bash
cd frontend
npm ci
npm run typecheck
npm run build
npm test -- src/components/maphub/weather/WeatherEngine.static.test.ts
```

Results:

```text
TypeScript passed
Vite production build passed
WeatherEngine.static.test.ts: 6 passed
```

## Packaging

`frontend/dist` is included.
`frontend/node_modules` is excluded.
