# Map Basemap Professional Hardening — 2026-07-03

## Summary

Added token-gated professional basemap support while preserving the secure default:

- Esri World Imagery remains the default free/available basemap.
- Mapbox Satellite Streets appears only when `VITE_MAPBOX_TOKEN` is configured.
- MapTiler Satellite appears only when `VITE_MAPTILER_KEY` is configured.
- Google Satellite remains documented but disabled until an official Google Map Tiles API session-token integration is implemented.

No commercial basemap is used as SAM2 input. These layers are display/background layers only.

## Security and licensing posture

- No unofficial Google tile URLs are used.
- Token-gated layers are hidden when keys are absent.
- MapLibre raster URLs are normalized with `toMapLibreRasterUrl()` to remove Leaflet-only placeholders such as `{s}` and `{r}`.
