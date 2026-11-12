"""Count valid native output pixels against a tenant-owned, versioned field boundary."""

import logging

logger = logging.getLogger("raster-service")


def measure_field_coverage(path, geometry, revision):
    """Include field cells beyond the source extent in the denominator.

    The ground grid is the output COG affine, extended when the COG covers only
    part of the field. Reading small windows limits memory use for large fields.
    """
    import numpy as np
    import rasterio
    from cog_writer import source_valid_mask, write_windows
    from raster_settings import RASTER_MAX_READ_BAND_PIXELS
    from rasterio.features import geometry_mask, geometry_window
    from rasterio.warp import transform_geom
    from rasterio.windows import Window, intersect

    if type(revision) is not int or revision < 0 or not isinstance(geometry, dict):
        return None
    if geometry.get("type") == "Feature":
        geometry = geometry.get("geometry")
    if not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        return None
    with rasterio.open(path) as src:
        if src.crs is None or src.count not in (1, 3, 4):
            return None
        geom = transform_geom("EPSG:4326", src.crs, geometry)
        field = geometry_window(src, [geom], boundless=True)
        if field.width * field.height > RASTER_MAX_READ_BAND_PIXELS:
            return None
        extent = Window(0, 0, src.width, src.height)
        field_pixels = valid_pixels = 0
        for tile in write_windows(int(field.height), int(field.width)):
            window = Window(
                field.col_off + tile.col_off, field.row_off + tile.row_off, tile.width, tile.height
            )
            inside = geometry_mask(
                [geom],
                (int(tile.height), int(tile.width)),
                src.window_transform(window),
                invert=True,
                all_touched=False,
            )
            field_pixels += int(inside.sum())
            if not inside.any() or not intersect(window, extent):
                continue
            overlap = window.intersection(extent)
            x = int(overlap.col_off - window.col_off)
            y = int(overlap.row_off - window.row_off)
            inside_overlap = inside[y : y + int(overlap.height), x : x + int(overlap.width)]
            if src.count == 1:
                samples = src.read(1, window=overlap, masked=True)
                valid = ~np.ma.getmaskarray(samples) & np.isfinite(samples.data)
            else:
                valid = source_valid_mask(src, overlap)
            valid_pixels += int((inside_overlap & valid).sum())
    if not field_pixels:
        return None
    return {
        "geometry_revision": revision,
        "denominator": "field_pixel_centres",
        "field_pixels": field_pixels,
        "valid_pixels": valid_pixels,
        "valid_pixel_ratio": valid_pixels / field_pixels,
    }


async def for_published_asset(req, stats, meta):
    """Bind the measurement to the saved geometry, never a client-supplied clip."""
    import db_persist

    path = (stats.get("cog") or {}).get("path")
    if (
        not path
        or not getattr(req, "tenant_id", None)
        or not (meta.get("spatial_sampling") or {}).get("output_pixel_size_m")
    ):
        return None
    try:
        saved = await db_persist.fetch_field_geometry_with_revision(req.field_id, req.tenant_id)
        if not saved:
            return None
        revision = saved.get("revision")
        requested_revision = getattr(req, "geometry_revision", None)
        if requested_revision is not None and revision != requested_revision:
            return None
        return measure_field_coverage(path, saved.get("geometry"), revision)
    except Exception as exc:
        # Missing coverage metadata must not invalidate an otherwise usable asset.
        logger.warning("field coverage unavailable for %s: %s", req.field_id, type(exc).__name__)
        return None
