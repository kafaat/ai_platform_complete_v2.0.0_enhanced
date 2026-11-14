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


def align_scenes_to_field_grid(scenes, geometry=None, revision=None):
    """Resample each scene COG onto one fixed field grid for the common valid mask.

    The grid is the earliest readable scene's CRS and pixel size. With the saved field
    geometry it spans the field window (``geometry_window``, boundless) and the field mask
    is the pixel centres inside the boundary, as in ``measure_field_coverage``. Without it
    the grid is that scene's extent and the field mask is the union of the scenes' valid
    pixels (declared as ``scene_valid_union``). Each scene is read masked (nodata, internal
    mask and non-finite values are invalid) and resampled with nearest neighbour, so an
    already aligned scene is copied unchanged. Blocking: call via ``run_raster_io``.
    """
    import numpy as np
    import rasterio
    from raster_settings import RASTER_MAX_READ_BAND_PIXELS
    from rasterio.features import geometry_mask, geometry_window
    from rasterio.warp import Resampling, reproject, transform_geom
    from rasterio.windows import Window

    if isinstance(geometry, dict) and geometry.get("type") == "Feature":
        geometry = geometry.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        geometry = None
    order = sorted(range(len(scenes)), key=lambda i: str(scenes[i].get("datetime") or ""))
    out = [
        {"datetime": sc.get("datetime"), "scene_id": sc.get("scene_id"), "values": None}
        for sc in scenes
    ]
    grid = None
    for i in order:
        sc = scenes[i]
        scene_revision = sc.get("geometry_revision")
        if not sc.get("path"):
            out[i]["excluded_reason"] = "source_asset_unknown"
            continue
        if (
            geometry is not None
            and type(revision) is int
            and type(scene_revision) is int
            and scene_revision != revision
        ):
            out[i]["excluded_reason"] = "geometry_revision_mismatch"
            continue
        try:
            with rasterio.open(sc["path"]) as src:
                if src.crs is None:
                    out[i]["excluded_reason"] = "scene_crs_unknown"
                    continue
                if src.width * src.height > RASTER_MAX_READ_BAND_PIXELS:
                    out[i]["excluded_reason"] = "scene_too_large"
                    continue
                if grid is None:
                    if geometry is not None:
                        geom = transform_geom("EPSG:4326", src.crs, geometry)
                        window = geometry_window(src, [geom], boundless=True)
                    else:
                        geom, window = None, Window(0, 0, src.width, src.height)
                    shape = (int(window.height), int(window.width))
                    if shape[0] * shape[1] * len(scenes) > RASTER_MAX_READ_BAND_PIXELS // 4:
                        return {"error": "field_grid_too_large"}
                    transform = src.window_transform(window)
                    field_mask = (
                        geometry_mask([geom], shape, transform, invert=True, all_touched=False)
                        if geom is not None
                        else None
                    )
                    grid = {
                        "crs": src.crs.to_string(),
                        "transform": list(transform)[:6],
                        "rows": shape[0],
                        "cols": shape[1],
                        "crs_obj": src.crs,
                        "transform_obj": transform,
                    }
                band = src.read(1, masked=True)
                data = band.astype("float32").filled(np.nan)
                if src.nodata is not None:
                    data[data == src.nodata] = np.nan
                data[~np.isfinite(data)] = np.nan
                dst = np.full((grid["rows"], grid["cols"]), np.nan, dtype="float32")
                reproject(
                    source=data,
                    destination=dst,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=grid["transform_obj"],
                    dst_crs=grid["crs_obj"],
                    src_nodata=np.nan,
                    dst_nodata=np.nan,
                    resampling=Resampling.nearest,
                )
                out[i]["values"] = dst
        except Exception as exc:  # noqa: BLE001 — one unreadable scene is excluded, not fatal
            logger.warning("common mask: scene unreadable (%s)", type(exc).__name__)
            out[i]["excluded_reason"] = "scene_unreadable"
    if grid is None:
        return {"error": "no_readable_scene"}
    basis = "saved_field_geometry"
    if field_mask is None:
        basis = "scene_valid_union"
        field_mask = np.zeros((grid["rows"], grid["cols"]), dtype=bool)
        for sc in out:
            if sc["values"] is not None:
                field_mask |= np.isfinite(sc["values"])
    grid = {k: v for k, v in grid.items() if not k.endswith("_obj")}
    return {"scenes": out, "field_mask": field_mask, "field_mask_basis": basis, "grid": grid}
