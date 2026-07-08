# P1 Raster Boundary Contract

This contract closes the first extraction seam after the P0 ownership guards.

## Boundary decision

`raster-service` is the owner of raster computation and raster runtime state.
`sahool-platform` may only act as a tenant-aware facade/proxy for browser-safe endpoints or as a consumer of raster summaries needed to assemble field cards.

## raster-service owns

- Sentinel/CDSE/STAC scene search and ranking.
- COG processing, validation, persistence and provenance.
- Raster assets, raster snapshots, raster registries and raster cache invalidation records.
- Vegetation indices and indicator grids: NDVI/NDMI/FVC/SAR/RVI/change detection.
- TileJSON, map tiles, thumbnails, terrain/hillshade/slope/contours.
- Field imagery available dates, historical backfill jobs and raster job status.

## sahool-platform may do

- Verify tenant/field ownership before proxying browser requests.
- Inject service-to-service headers such as `X-Agent-Token`, tenant id and field id.
- Aggregate raster outputs into field intelligence, AI context or UI cards.
- Mark raster cache stale when field geometry changes; the raster service/worker owns recomputation.

## sahool-platform must not do

- Compute NDVI or other raster indices from bands.
- Create new raster/STAC/COG/Tile endpoints as platform-owned domain endpoints.
- Write directly to raster-owned tables, except through explicitly reviewed legacy migration code that is being retired.
- Import internal modules from `services/raster-service`.
- Invent imagery dates, scene ids, cloud metrics or acquisition timestamps when raster-service is unavailable.

## Allowed platform raster facade files

The allowlist is machine-checked in `docs/architecture/raster_boundary_allowlist.json`.
Any new platform file that references raster concepts must be added deliberately and reviewed as either:

- `facade_proxy`: external route proxy to raster-service.
- `service_client`: internal service-to-service client.
- `field_geometry_signal`: field geometry change invalidation only.
- `aggregation_consumer`: reads raster facts to build field/AI context.
- `legacy_compat`: temporary backward compatibility route.

## Migration path

1. Keep the current facade routes stable.
2. Move remaining raster computation/read logic out of platform in small PRs.
3. Switch web/mobile clients to gateway routes that target raster-service directly where safe.
4. Remove legacy compatibility routes after a deprecation window.
