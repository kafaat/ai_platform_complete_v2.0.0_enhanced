"""Decode a catalogue-bound, single-band Landsat C2 L2 surface temperature window."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from datetime import datetime
from urllib.parse import urlsplit

import db_persist
import raster_settings
import raster_stage_receipt
from fastapi import HTTPException

SCALE = 0.00341802
OFFSET = 149.0
QA_VERSION = "landsat-c2-qa-pixel-bits0-5/1"


def reject(code):
    raise HTTPException(422, {"code": "landsat_lst_" + code})


def select_asset(assets, keys):
    matches = [
        (k, a)
        for k, a in assets.items()
        if k.lower() in keys and isinstance(a, dict) and a.get("href")
    ]
    return matches[0] if len(matches) == 1 else (None, {})


def catalog_contract(feat, key, asset):
    band_list = asset.get("raster:bands")
    props = feat.get("properties") or {}
    if (
        feat.get("collection") != "landsat-c2-l2"
        or props.get("landsat:correction") != "L2SP"
        or not isinstance(band_list, list)
        or len(band_list) != 1
        or not isinstance(band_list[0], dict)
    ):
        return None
    return {
        "collection": feat["collection"],
        "scene": feat.get("id"),
        "acquired": props.get("datetime"),
        "key": key,
        "href": asset["href"],
        "band": band_list[0],
        "gsd": asset.get("gsd"),
        "checksum": asset.get("file:checksum"),
        "qa": (feat.get("assets") or {}).get("qa_pixel"),
    }


def product_identity(tenant, field, geometry, revision, provider, scene_id, contract, mask):
    from indicator_batch_claim import geometry_hash
    from indicator_product_identity import ProductIdentity

    from shared.contracts.remote_sensing.thermal import LANDSAT_ST_KELVIN

    # Same item id can have a reissued asset. Exclude temporary access signatures
    # from its identity and include the authorized field even for coincident shapes.
    qa = (contract.get("qa") or {}) if mask else {}

    def permanent_ref(href):
        return (href or "").split("?", 1)[0].split("#", 1)[0]

    inputs = [
        field,
        contract["collection"],
        contract["key"],
        contract["band"],
        contract["acquired"],
        permanent_ref(contract["href"]),
        contract["checksum"],
        contract.get("gsd"),
        permanent_ref(qa.get("href")),
        qa.get("file:checksum"),
    ]
    digest = hashlib.sha256(
        json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ProductIdentity(
        str(tenant),
        geometry_hash(geometry, revision),
        scene_id,
        "lst",
        LANDSAT_ST_KELVIN,
        QA_VERSION if mask else None,
        provider=provider,
        input_digest=digest,
    )


def _source(ctx, href):
    if not isinstance(href, str):
        reject("asset_missing")
    # Earth Search publishes requester-pays S3 COGs. Preserve GDAL's normal
    # credential/billing configuration and restrict this exception to official L2 assets.
    if href.startswith("s3://usgs-landsat/collection02/level-2/standard/") and not any(
        token in href for token in ("..", "?", "#", "\\")
    ):
        return href
    if urlsplit(href).scheme != "https":
        reject("unsupported_catalogue_uri")
    return ctx._safe_raster_source(href)


def _polygon(data):
    from shapely.geometry import shape

    if not isinstance(data, dict) or data.get("type") not in ("Polygon", "MultiPolygon"):
        reject("invalid_field_geometry")
    polys = (
        [data["coordinates"]]
        if data.get("type") == "Polygon" and "coordinates" in data
        else data.get("coordinates")
    )
    try:
        if not polys or not all(
            ring and len(ring) >= 4 and ring[0] == ring[-1] for poly in polys for ring in poly
        ):
            reject("invalid_field_geometry")
        geom = shape(data)
    except (ValueError, TypeError, IndexError, KeyError):
        reject("invalid_field_geometry")
    if geom.is_empty or not geom.is_valid or geom.has_z or geom.area <= 0:
        reject("invalid_field_geometry")
    west, south, east, north = geom.bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        reject("invalid_field_geometry")
    return geom


def _field(req):
    if not req.tenant_id or not req.field_id:
        reject("tenant_field_required")
    clip = _polygon(req.clip_polygon_geojson)
    stored = asyncio.run(db_persist.fetch_field_geometry_with_revision(req.field_id, req.tenant_id))
    if not stored:
        raise HTTPException(404, "landsat_lst_field_unavailable")
    if stored["revision"] != req.geometry_revision:
        raise HTTPException(409, "landsat_lst_field_revision_changed")
    if not _polygon(stored["geometry"]).covers(clip):
        raise HTTPException(403, "landsat_lst_clip_outside_field")
    return clip.__geo_interface__


def _encoding(src, band):
    dtype = band.get("data_type")
    unit = str(band.get("unit")).lower()
    scale, offset, fill = (band.get(k) for k in ("scale", "offset", "nodata"))
    if (
        src.count != 1
        or not src.crs
        or src.dtypes[0] != dtype
        or unit not in ("kelvin", "k")
        or isinstance(fill, bool)
        or not isinstance(fill, (float, int))
        or not math.isfinite(fill)
        or (src.nodata is not None and src.nodata != fill)
    ):
        reject("band_metadata_conflict")
    raw = dtype == "uint16" and (scale, offset, fill) == (SCALE, OFFSET, 0)
    calibrated = dtype in ("float32", "float64") and (scale, offset) == (1, 0)
    if not (raw or calibrated) or isinstance(scale, bool) or isinstance(offset, bool):
        reject("ambiguous_encoding")
    # Rasterio read() returns stored samples even if GDAL reports a scale/offset.
    # Default identity tags on a raw USGS TIFF convey no override of STAC.
    if (src.scales[0], src.offsets[0]) not in ((1, 0), (scale, offset)) or (
        src.units[0] and src.units[0].strip().lower() not in ("kelvin", "k")
    ):
        reject("tiff_metadata_conflict")
    return raw, fill


def _read_qa(ctx, asset, src, window, inside):
    import numpy as np
    import rasterio

    if not isinstance(asset, dict) or not asset.get("href"):
        reject("qa_pixel_missing")
    path = _source(ctx, asset.get("href"))
    with rasterio.open(path) as qa:
        if (
            qa.count != 1
            or qa.dtypes[0] != "uint16"
            or qa.crs != src.crs
            or qa.transform != src.transform
            or qa.shape != src.shape
        ):
            reject("qa_grid_mismatch")
        samples = qa.read(1, window=window, masked=True)
    bits = samples.data
    observed = inside & ~np.ma.getmaskarray(samples) & ((bits & 1) == 0)
    clear = observed & ((bits & 0b111110) == 0)
    cloudy = observed & ((bits & 0b001110) != 0)
    cloud_pct = 100 * int(cloudy.sum()) / int(observed.sum()) if observed.any() else None
    return (
        clear,
        cloud_pct,
        raster_stage_receipt.asset_integrity(
            "qa_pixel", urlsplit(asset["href"]).path, asset.get("file:checksum"), path
        ),
    )


def read(ctx, req):
    import numpy as np
    import rasterio
    from rasterio.errors import WindowError
    from rasterio.features import geometry_mask, geometry_window
    from rasterio.warp import transform_geom

    contract = getattr(req, "_landsat_st", None)
    if (
        not contract
        or contract["href"] != req.raster_url
        or not req.scene_id
        or contract["scene"] != req.scene_id
        or not req.capture_datetime
        or contract["acquired"] != req.capture_datetime
    ):
        reject("catalogue_contract_required")
    try:
        acquired = datetime.fromisoformat(req.capture_datetime.replace("Z", "+00:00"))
        if acquired.utcoffset() is None:
            reject("acquisition_missing_timezone")
    except ValueError:
        reject("invalid_acquisition")
    geometry = _field(req)
    path = _source(ctx, req.raster_url)
    band = contract["band"]
    with rasterio.open(path) as src:
        raw, fill = _encoding(src, band)
        geom = transform_geom("EPSG:4326", src.crs, geometry)
        try:
            window = geometry_window(src, [geom])
        except WindowError:
            reject("field_outside_scene")
        h, w = int(window.height), int(window.width)
        if h * w > raster_settings.RASTER_MAX_READ_BAND_PIXELS:
            raise HTTPException(413, "landsat_lst_window_too_large")
        transform = src.window_transform(window)
        inside = geometry_mask([geom], (h, w), transform, invert=True, all_touched=False)
        data = src.read(1, window=window, masked=True)
        values = data.data
        valid = inside & ~np.ma.getmaskarray(data) & np.isfinite(values) & (values != fill)
        # The USGS valid stored range is 293..65535. Include the same endpoints
        # after float32 rounding when the provider already supplied Kelvin.
        if raw:
            valid &= values >= 293
        else:
            low, high = (np.float32(dn * SCALE + OFFSET) for dn in (293, 65535))
            valid &= (values >= min(low.item(), 293 * SCALE + OFFSET)) & (
                values <= max(high.item(), 65535 * SCALE + OFFSET)
            )
        integrity = [
            raster_stage_receipt.asset_integrity(
                contract["key"], urlsplit(req.raster_url).path, contract["checksum"], path
            )
        ]
        cloud_pct = None
        if req.apply_cloud_mask:
            clear, cloud_pct, record = _read_qa(ctx, contract["qa"], src, window, inside)
            valid &= clear
            integrity.append(record)
        if raster_stage_receipt.integrity_mismatches(integrity):
            reject("asset_integrity_mismatch")
        arr = np.full((h, w), np.nan, dtype="float32")
        samples = values[valid].astype("float64")
        arr[valid] = samples * SCALE + OFFSET if raw else samples
        crs = src.crs
        area = None
        if crs.is_projected:
            factor = crs.linear_units_factor[1]
            area = int(valid.sum()) * abs(transform.determinant) * factor**2
    receipt = {
        "collection": contract["collection"],
        "asset_key": contract["key"],
        "scene_id": req.scene_id,
        "acquisition_datetime": req.capture_datetime,
        "encoding": "dn" if raw else "kelvin",
        "scale": band["scale"],
        "offset": band["offset"],
        "nodata": fill,
        "unit": "K",
        "field_pixels": int(inside.sum()),
        "valid_area_m2": area,
        "declared_grid_resolution_m": band.get("spatial_resolution"),
        "sensor_gsd_m": contract["gsd"],
        "qa_mask_version": QA_VERSION if req.apply_cloud_mask else None,
        "cloud_pct": cloud_pct,
        "asset_integrity": integrity,
    }
    return arr, transform, crs, receipt
