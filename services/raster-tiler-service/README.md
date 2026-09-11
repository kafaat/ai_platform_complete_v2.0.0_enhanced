# raster-tiler-service

TiTiler-compatible COG/MosaicJSON tile service for SAHOOL Phase 4.

Default internal URL: `http://raster-tiler-service:8088`.
The platform exposes TileJSON through `/api/v1/gis/cloud-native/rasters/{id}/tilejson.json`.
Its tile URLs identify a registry record at `/api/v1/gis/cloud-native/rasters/{id}/tiles/{z}/{x}/{y}.png`.
The platform resolves that record under tenant RLS before calling this service through
`TITILER_URL`. Raster layer tiles use their existing tenant-authorized route and the
same backend. Neither API exposes the internal host or accepts a browser-supplied COG URL.

Set `COG_TILE_ALLOWED_HOSTS` to exact, trusted public HTTPS COG source hosts.
An empty list returns `503 cog_tile_backend_not_configured`; disallowed or private
sources return `422 cog_tile_source_not_allowed`. Bucket-wide private object access
is not authorized by this setting. Browser clients must send their existing API
authentication on tile requests. No public `/tiler` catch-all is installed.

The v9 service joins `sahool-internal`. The older `sahool-titiler` image is available
only with the `legacy-tiler` profile for explicit compatibility deployments.

`TITILER_BASE_URL` was the former URL-construction setting. Registry TileJSON now uses the authenticated platform route; configure the server-side transport with `TITILER_URL`.
