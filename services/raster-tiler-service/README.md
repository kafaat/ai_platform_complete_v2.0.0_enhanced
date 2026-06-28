# raster-tiler-service

TiTiler-compatible COG/MosaicJSON tile service for SAHOOL Phase 4.

Default internal URL: `http://raster-tiler-service:8088`.
The platform exposes TileJSON through `/api/v1/gis/cloud-native/rasters/{id}/tilejson.json` and points tiles to this service via `TITILER_BASE_URL`.
