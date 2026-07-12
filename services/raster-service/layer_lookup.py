"""Field-scoped raster layer lookup and COG grid helpers.

Extracted from ``main.py`` as phase 3 of raster-service decomposition.  The
functions are intentionally dependency-injected for the mutable in-memory maps
(``_layers``/``_field_layers``), tenant context, logger, and object store.  This
keeps public ``main._*`` compatibility wrappers small while avoiding importing
``main`` from this module.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

GRID_INDEX_ALIASES = {
    "salinity": "ndsi",
    "salt": "ndsi",
    "soil_salinity": "ndsi",
    "ndvu": "ndvi",
    "vegetation": "ndvi",
    "moisture": "ndmi",
}


def normalize_index(index: str | None) -> str:
    key = (index or "ndvi").strip().lower().replace(" ", "_").replace("-", "_")
    return GRID_INDEX_ALIASES.get(key, key)


def display_index(index: str | None) -> str:
    key = (index or "ndvi").strip().lower().replace(" ", "_").replace("-", "_")
    if key in ("salinity", "salt", "soil_salinity"):
        return "salinity"
    if key == "ndvu":
        return "ndvi"
    return key


def find_field_layer(
    layers: dict[str, dict[str, Any]],
    field_layers: dict[str, list[str]],
    field_id: str,
    index: str,
    date: str,
) -> dict[str, Any] | None:
    """Find a persisted COG-backed layer for ``field_id``/``index``/``date``.

    ``date='latest'`` returns the newest acquisition date.  A concrete
    YYYY-MM-DD date is strict and never falls back to latest.
    """
    layer_ids = field_layers.get(field_id, [])
    internal = normalize_index(index)
    candidates: list[dict[str, Any]] = []
    for layer_id in layer_ids:
        layer = layers.get(layer_id)
        if not layer or not layer.get("cog_url"):
            continue
        if layer.get("index") != internal:
            continue
        candidates.append(layer)
    if not candidates:
        return None
    if date and date != "latest":
        dated = [c for c in candidates if (c.get("acquisition_date") or "").startswith(date)]
        if not dated:
            return None
        candidates = dated
    candidates.sort(
        key=lambda c: (str(c.get("acquisition_date") or ""), str(c.get("created_at") or "")),
        reverse=True,
    )
    return candidates[0]


def grid_from_cog(
    layer: dict[str, Any],
    index: str,
    date: str,
    grid: int,
    object_store_module: Any,
) -> dict[str, Any] | None:
    """Read a COG and downsample it to a classified grid.

    Returns ``None`` honestly when rasterio/COG access is unavailable.
    """
    try:
        import indicator_grid as ig
        import numpy as np
        import rasterio
        from rasterio.warp import transform_bounds
    except Exception:  # noqa: BLE001
        return None

    cog_url = layer["cog_url"]
    path = object_store_module.to_gdal_path(cog_url)
    try:
        with rasterio.open(path) as src:
            arr = src.read(1).astype("float64")
            if src.nodata is not None:
                arr = np.where(arr == src.nodata, np.nan, arr)
            if src.crs is not None:
                bbox = list(transform_bounds(src.crs, "EPSG:4326", *src.bounds))
            else:
                bbox = list(src.bounds)
    except Exception:  # noqa: BLE001
        return None

    part = ig.grid_from_array(arr, index, grid)
    result = {
        "field_id": layer.get("field_id") or "",
        "index": index,
        "date": (layer.get("acquisition_date") or date),
        "bbox": [round(float(x), 6) for x in bbox],
        "rows": part["rows"],
        "cols": part["cols"],
        "grid": part["grid"],
        "stats": part["stats"],
        "zones": part["zones"],
        "source": layer.get("source_format") or "raster",
        "real_data": True,
        "cloud_pct": layer.get("cloud_pct"),
        "cloud_cover": layer.get("cloud_cover"),
        "valid_pixel_ratio": layer.get("valid_pixel_ratio"),
        "coverage_ratio": layer.get("coverage_ratio"),
        "index_quality_flags": layer.get("index_quality_flags"),
        "confidence": layer.get("confidence"),
        "quality": layer.get("quality"),
    }
    # Surface the typed provenance/quality envelope onto the wire alongside the
    # existing (unchanged) contract keys. source="raster-service", estimated=False,
    # quality gate passed. Provenance is built only from real layer metadata —
    # never fabricated (absent fields stay None).
    import raster_indicator_product as rip
    from raster_validated_product import ProvenanceRecord

    provenance = None
    if any(layer.get(k) for k in ("scene_id", "cog_url", "source_format")):
        from raster_quality import ALGORITHM_VERSION

        _vpr = layer.get("valid_pixel_ratio")
        provenance = ProvenanceRecord(
            source=layer.get("source_format"),
            source_format=layer.get("source_format"),
            scene_id=layer.get("scene_id"),
            capture_datetime=layer.get("acquisition_date"),
            acquisition_datetime=layer.get("acquisition_date"),
            # this grid was computed by THIS band-math implementation; the QA-mask
            # identity is only published when the layer actually recorded one.
            algorithm_version=ALGORITHM_VERSION,
            qa_mask_version=layer.get("qa_mask_version"),
            valid_pixel_pct=round(float(_vpr) * 100.0, 3) if _vpr is not None else None,
            source_uri=layer.get("cog_url"),
        )
    result["indicator_product"] = rip.from_grid_response(
        result,
        quality_score=layer.get("confidence"),
        provenance=provenance,
    )
    return result


async def rehydrate_field_layer_from_db(
    field_id: str,
    internal: str,
    date: str,
    *,
    layers: dict[str, dict[str, Any]],
    field_layers: dict[str, list[str]],
    tenant_getter: Callable[[], str | None],
    logger: Any,
    object_store_module: Any,
) -> dict[str, Any] | None:
    """Restore a COG layer from ``raster_assets`` into in-memory layer maps."""
    try:
        import time as _time

        import db_persist

        tenant_id = tenant_getter()
        asset = await db_persist.fetch_latest_asset(field_id, internal, date, tenant_id=tenant_id)
        if not asset or not asset.get("cog_url"):
            return None
        if not object_store_module.exists_locally(asset["cog_url"]):
            logger.warning("raster_assets hit but COG missing on host: %s", asset["cog_url"])
            return None
        acquisition_date = asset.get("acquisition_date")
        layer_id = f"db_{field_id}_{internal}_{acquisition_date or 'nodate'}"
        layers[layer_id] = {
            "cog_url": asset["cog_url"],
            "index": internal,
            "field_id": field_id,
            "tenant_id": tenant_id,
            "acquisition_date": acquisition_date,
            "bounds_4326": asset.get("bounds_4326"),
            "cloud_pct": asset.get("cloud_pct"),
            "cloud_cover": asset.get("cloud_cover"),
            "valid_pixel_ratio": asset.get("valid_pixel_ratio"),
            "coverage_ratio": asset.get("coverage_ratio"),
            "index_quality_flags": asset.get("index_quality_flags"),
            "confidence": asset.get("confidence"),
            "quality": asset.get("quality"),
            "cloud_mask_applied": asset.get("cloud_mask_applied"),
            "scene_id": asset.get("scene_id"),
            "geometry_revision": asset.get("geometry_revision"),
            "asset_status": asset.get("asset_status"),
            "processing_job_id": asset.get("processing_job_id"),
            "created_at": acquisition_date or _time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        field_layers.setdefault(field_id, [])
        if layer_id not in field_layers[field_id]:
            field_layers[field_id].append(layer_id)
        return layers[layer_id]
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB rehydrate skipped (%s): %s", field_id, exc)
        return None


async def resolve_field_layer(
    field_id: str,
    index: str,
    date: str,
    *,
    layers: dict[str, dict[str, Any]],
    field_layers: dict[str, list[str]],
    tenant_getter: Callable[[], str | None],
    logger: Any,
    object_store_module: Any,
) -> dict[str, Any] | None:
    """Resolve a field layer from memory or DB with strict-date semantics."""
    internal = normalize_index(index)
    mem = find_field_layer(layers, field_layers, field_id, index, date)

    if date and date != "latest":
        if mem is not None:
            return mem
        return await rehydrate_field_layer_from_db(
            field_id,
            internal,
            date,
            layers=layers,
            field_layers=field_layers,
            tenant_getter=tenant_getter,
            logger=logger,
            object_store_module=object_store_module,
        )

    db_layer = await rehydrate_field_layer_from_db(
        field_id,
        internal,
        "latest",
        layers=layers,
        field_layers=field_layers,
        tenant_getter=tenant_getter,
        logger=logger,
        object_store_module=object_store_module,
    )
    if db_layer is None:
        return mem
    if mem is None:
        return db_layer
    mem_date = str(mem.get("acquisition_date") or "")
    db_date = str(db_layer.get("acquisition_date") or "")
    return mem if mem_date >= db_date else db_layer


async def rvi_from_sar_cog(
    field_id: str,
    date: str,
    *,
    layers: dict[str, dict[str, Any]],
    field_layers: dict[str, list[str]],
    tenant_getter: Callable[[], str | None],
    logger: Any,
    object_store_module: Any,
) -> float | None:
    """Compute RVI from a dual-band SAR COG if one exists."""
    layer = await resolve_field_layer(
        field_id,
        "rvi",
        date,
        layers=layers,
        field_layers=field_layers,
        tenant_getter=tenant_getter,
        logger=logger,
        object_store_module=object_store_module,
    )
    if layer is None:
        layer = await resolve_field_layer(
            field_id,
            "sar",
            date,
            layers=layers,
            field_layers=field_layers,
            tenant_getter=tenant_getter,
            logger=logger,
            object_store_module=object_store_module,
        )
    if layer is None:
        return None
    try:
        import numpy as np
        import rasterio
        import sar_rvi
    except Exception:  # noqa: BLE001
        return None
    path = object_store_module.to_gdal_path(layer["cog_url"])
    try:
        with rasterio.open(path) as src:
            if src.count < 2:
                return None
            vv = src.read(1).astype("float64")
            vh = src.read(2).astype("float64")
            if src.nodata is not None:
                vv = np.where(vv == src.nodata, np.nan, vv)
                vh = np.where(vh == src.nodata, np.nan, vh)
    except Exception:  # noqa: BLE001
        return None
    result = sar_rvi.compute_rvi(vv, vh, in_db=False)
    return result["rvi_mean"] if result["valid_pixels"] else None


async def real_field_grid(
    field_id: str,
    index: str,
    date: str,
    grid: int,
    *,
    layers: dict[str, dict[str, Any]],
    field_layers: dict[str, list[str]],
    tenant_getter: Callable[[], str | None],
    logger: Any,
    object_store_module: Any,
) -> dict[str, Any] | None:
    """Return a real COG-backed field grid, never a simulated fallback."""
    layer = await resolve_field_layer(
        field_id,
        index,
        date,
        layers=layers,
        field_layers=field_layers,
        tenant_getter=tenant_getter,
        logger=logger,
        object_store_module=object_store_module,
    )
    if layer is None:
        return None
    return grid_from_cog(layer, index, date, grid, object_store_module)
