"""routers/cdse_tiles.py — بلاطات CDSE الحيّة ومعالجة CDSE (CDSE Live Tiles)."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlencode

import cdse_client as _cdse
import db_persist as _db
import raster_cdse_tile_runtime as _cdse_rt
import raster_date_geo
from fastapi import APIRouter, Query
from fastapi.responses import Response
from raster_runtime_state import FIELD_LAYERS, LAYERS
from raster_security_context import REQ_TENANT, require_field_tenant
from raster_settings import TRANSPARENT_PNG

router = APIRouter()
logger = logging.getLogger("raster-service")

# بادئة البوّابة العامّة في روابط TileJSON: الواجهة تصل عبر nginx ``/api/raster/`` لا
# ``/v1/`` المباشر، فمصفوفة ``tiles`` يجب أن تحمل البادئة لتُحلّ من أصل الصفحة.
_PUBLIC_PREFIX = os.getenv("RASTER_PUBLIC_PREFIX", "/api/raster").rstrip("/")


async def _require_field(field_id: str) -> None:
    await require_field_tenant(field_id, layers=LAYERS, field_layers=FIELD_LAYERS, logger=logger)


# Backwards-compatible helper names retained for tests/imports while implementation lives outside router.
_parse_poly = _cdse_rt.parse_poly
_normalize_cdse_request = _cdse_rt.normalize_cdse_request
_tilejson_availability = _cdse_rt.tilejson_availability


async def _ensure_field_cog(*args, **kwargs):
    return await _cdse_rt.ensure_field_cog(*args, logger=logger, **kwargs)


@router.get("/v1/fields/{field_id}/cdse-tiles/{z}/{x}/{y}.png")
async def field_cdse_tile(
    field_id: str,
    z: int,
    x: int,
    y: int,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    bbox_w: float | None = Query(None),
    bbox_s: float | None = Query(None),
    bbox_e: float | None = Query(None),
    bbox_n: float | None = Query(None),
    poly: str | None = Query(None),
):
    """بلاطة Sentinel Hub حيّة: تجلب COG مقصوص للحقل وتصيّر بلاطة XYZ."""
    await _require_field(field_id)

    params = await _normalize_cdse_request(
        field_id, index, date, (bbox_w, bbox_s, bbox_e, bbox_n), poly
    )
    if params is None:
        return Response(content=TRANSPARENT_PNG, media_type="image/png")
    internal = params["internal"]
    field_bbox = params["field_bbox"]

    if field_bbox:
        try:
            from rasterio.warp import transform_bounds as _tb
            from tile_render import tile_bounds_3857

            b3857 = tile_bounds_3857(z, x, y)
            tw, ts, te, tn = _tb("EPSG:3857", "EPSG:4326", *b3857)
            fw, fs, fe, fn = field_bbox
            if te < fw or tw > fe or tn < fs or ts > fn:
                return Response(content=TRANSPARENT_PNG, media_type="image/png")
        except Exception:  # noqa: BLE001
            pass

    cog_path = await _ensure_field_cog(
        field_id,
        internal,
        params["today"],
        params["date_from"],
        params["date_to"],
        field_bbox,
        params["field_geom"],
        params["has_poly"],
    )
    if cog_path is None:
        return Response(content=TRANSPARENT_PNG, media_type="image/png")

    try:
        import tile_render

        png = tile_render.render_tile_png(cog_path, z, x, y, internal)
        if png:
            return Response(
                content=png,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=3600"},
            )
        logger.info(
            "cdse-tile شفّاف: لا بيانات صالحة في البلاطة (%s/%s z%s/%s/%s)",
            field_id,
            internal,
            z,
            x,
            y,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("CDSE tile render failed (%s): %s", field_id, e)

    return Response(content=TRANSPARENT_PNG, media_type="image/png")


@router.get("/v1/fields/{field_id}/cdse-thumbnail.png")
async def field_cdse_thumbnail(
    field_id: str,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    bbox_w: float | None = Query(None),
    bbox_s: float | None = Query(None),
    bbox_e: float | None = Query(None),
    bbox_n: float | None = Query(None),
    poly: str | None = Query(None),
    size: int = Query(160, ge=48, le=512),
):
    """مُصغَّرة كاملة لصورة الحقل (مؤشّر) لتاريخ مُعطى."""
    await _require_field(field_id)

    params = await _normalize_cdse_request(
        field_id, index, date, (bbox_w, bbox_s, bbox_e, bbox_n), poly
    )
    if params is None:
        return Response(content=TRANSPARENT_PNG, media_type="image/png")

    cog_path = await _ensure_field_cog(
        field_id,
        params["internal"],
        params["today"],
        params["date_from"],
        params["date_to"],
        params["field_bbox"],
        params["field_geom"],
        params["has_poly"],
    )
    if cog_path is None:
        return Response(content=TRANSPARENT_PNG, media_type="image/png")

    try:
        import tile_render

        png = tile_render.render_cog_thumbnail_png(cog_path, params["internal"], max_px=size)
        if png:
            return Response(
                content=png,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=3600"},
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("CDSE thumbnail render failed (%s): %s", field_id, e)

    return Response(content=TRANSPARENT_PNG, media_type="image/png")


@router.get("/v1/fields/{field_id}/cdse-tilejson")
async def field_cdse_tilejson(
    field_id: str,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    bbox_w: float | None = Query(None),
    bbox_s: float | None = Query(None),
    bbox_e: float | None = Query(None),
    bbox_n: float | None = Query(None),
    poly: str | None = Query(None),
):
    """TileJSON 2.2.0 لبلاطات CDSE الحيّة."""
    await _require_field(field_id)

    _GLOBAL_BOUNDS = [-180.0, -85.0, 180.0, 85.0]
    geom_resolved = True
    poly_geom = _parse_poly(poly) if isinstance(poly, str) and poly else None
    if poly_geom is not None:
        bounds = raster_date_geo.bbox_from_geom(poly_geom) or _GLOBAL_BOUNDS
        geom_resolved = bounds is not _GLOBAL_BOUNDS
    elif all(isinstance(v, (int, float)) for v in (bbox_w, bbox_s, bbox_e, bbox_n)):
        bounds = [float(bbox_w), float(bbox_s), float(bbox_e), float(bbox_n)]
    else:
        field_geom = await _db.fetch_field_geometry(field_id)
        bounds = raster_date_geo.bbox_from_geom(field_geom) or _GLOBAL_BOUNDS
        geom_resolved = bounds is not _GLOBAL_BOUNDS

    specific_date = date if (date and date not in ("latest", "today")) else None
    tile_params: dict[str, str] = {"index": index}
    if specific_date:
        tile_params["date"] = specific_date
    req_tenant = REQ_TENANT.get()
    if req_tenant:
        tile_params["tid"] = req_tenant
    if poly:
        tile_params["poly"] = poly
    elif bbox_w is not None and bbox_s is not None and bbox_e is not None and bbox_n is not None:
        tile_params["bbox_w"] = str(bbox_w)
        tile_params["bbox_s"] = str(bbox_s)
        tile_params["bbox_e"] = str(bbox_e)
        tile_params["bbox_n"] = str(bbox_n)
    qs = urlencode(tile_params)

    configured = _cdse.is_configured()
    available, reason, user_message = _tilejson_availability(configured, index)
    if available and not geom_resolved:
        available = False
        reason = reason or "field_geometry_unavailable"
        user_message = user_message or (
            "تعذّر تحديد حدود الحقل (لا poly/bbox ولا هندسة محفوظة) — مرّر هندسة الحقل أو "
            "تحقّق من حفظ الحدود قبل عرض بلاطات CDSE."
        )
    out = {
        "tilejson": "2.2.0",
        "name": f"cdse-{field_id}-{index}",
        "scheme": "xyz",
        "tiles": [f"{_PUBLIC_PREFIX}/v1/fields/{field_id}/cdse-tiles/{{z}}/{{x}}/{{y}}.png?{qs}"],
        "minzoom": 10,
        "maxzoom": 18,
        "bounds": bounds,
        "center": [
            round((bounds[0] + bounds[2]) / 2.0, 6),
            round((bounds[1] + bounds[3]) / 2.0, 6),
            14,
        ],
        "available": available,
    }
    if reason:
        out["reason"] = reason
    if user_message:
        out["user_message"] = user_message
    return out
