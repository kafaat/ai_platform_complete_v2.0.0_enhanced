# SAHOOL Weather Map Engine

Open-Meteo is used as the data source only. SAHOOL renders:

- Leaflet GridLayer SVG weather tiles
- wind animation inside tiles
- weather/operation layer controls
- time selector
- color legend
- click probe popup
- agronomic operation suitability layers

Current integration entrypoint: `../OverlayMarkers.tsx` / `WeatherRasterOverlay`.

Recommended next refactor when frontend build tooling is available:

- `WeatherTileLayer.ts`
- `WeatherLayerControls.tsx`
- `WeatherLegend.tsx`
- `WeatherProbePopup.tsx`
- `palettes.ts`
- `layerDefinitions.ts`
