# P6 Gateway Split Contract

Sahool platform is no longer the intended universal transit hop for extracted domains.

## Target routing

- `frontend → gateway → raster-service` for imagery, COG, tiles, indices, terrain.
- `frontend → gateway → weather-service` for weather core, operation windows, tiles, wind grids.
- `frontend → gateway → decision-service` for decision, dispatch, outcome, learning lineage.
- `frontend → gateway → sahool-platform` only for BFF aggregation, auth-shaped views, legacy compatibility, and orchestration that has not yet been extracted.

## Rule

Gateway route declarations must not point new raster/weather/decision domain routes back into `sahool-platform` unless the route is explicitly marked legacy/BFF in the ownership map.
