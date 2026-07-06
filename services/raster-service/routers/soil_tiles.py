"""
routers/soil_tiles.py — طبقة تربة SoilGrids كبلاطات Raster (توجيه اختيار العيّنات).

  • GET /v1/soil/tiles/{prop}/{depth}/{z}/{x}/{y}.png — بلاطة خاصّيّة ملوّنة (شفّافة بلا مصدر)
  • GET /v1/soil/tilejson?property=&depth=  — TileJSON + available + legend + تحذير إلزاميّ
  • GET /v1/soil/properties                 — الخصائص/الأعماق المدعومة + هل المصدر مُهيّأ

صدق صارم: بلا ``SOILGRIDS_DIR`` مُهيّأ ⇒ بلاطة شفّافة + ``available:false`` + سبب. التحذير
(SoilGrids تقديريّ ~250م، لا يُغني عن المختبر) يُرفَق دائماً كي لا تُستعمل الطبقة كبديل عن
التحليل. auth كبلاطات CDSE: ``tid`` في الرابط ⇒ سياق مستأجِر؛ بلا سياق ⇒ شفّاف.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

import soil_render as _soil
from fastapi import APIRouter, Query, Response
from raster_runtime_state import FIELD_LAYERS, LAYERS
from raster_security_context import REQ_TENANT, require_field_tenant
from raster_settings import TRANSPARENT_PNG

logger = logging.getLogger("raster-service")

router = APIRouter()

_PUBLIC_PREFIX = os.getenv("RASTER_PUBLIC_PREFIX", "/api/raster").rstrip("/")


def _tenant_ctx_ok() -> bool:
    return REQ_TENANT.get() is not None


@router.get("/v1/soil/tiles/{prop}/{depth}/{z}/{x}/{y}.png")
async def soil_tile(
    prop: str, depth: str, z: int, x: int, y: int, tid: Annotated[str | None, Query()] = None
):
    """بلاطة خاصّيّة تربة ملوّنة. شفّافة عند غياب المصدر/السياق (fail-closed صادق)."""
    if not _tenant_ctx_ok():
        return Response(content=TRANSPARENT_PNG, media_type="image/png")
    png = _soil.render_soil_tile(prop, _soil.normalize_depth(depth), z, x, y)
    return Response(
        content=png or TRANSPARENT_PNG,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/v1/soil/tilejson")
async def soil_tilejson(
    property: Annotated[str, Query()] = "phh2o", depth: Annotated[str, Query()] = "0-5cm"
):
    """TileJSON لطبقة خاصّيّة تربة — يستهلكه Leaflet/MapLibre.

    ``available`` يعكس تهيئة المصدر لهذه (الخاصّيّة، العمق) فعليّاً. ``disclaimer`` إلزاميّ
    دائماً (الطبقة توجيهيّة لا بديلة عن المختبر).

    ملاحظة مصادقة (v31.9): روابط ``tiles`` **بيانات وصفيّة** (tid فقط)؛ خلف بوّابة
    ``/api/raster/`` تحتاج البلاطة توكناً — تبنيه الواجهة عبر ``soilTileUrl`` (تُضيف
    access_token). لا تُستهلَك ``tiles`` مباشرةً بلا حقن توكن.
    """
    prop = property if property in _soil.SOIL_PROPERTIES else "phh2o"
    depth = _soil.normalize_depth(depth)
    meta = _soil.SOIL_PROPERTIES[prop]
    available = _soil.soil_raster_path(prop, depth) is not None
    tenant = REQ_TENANT.get()
    tid_q = f"?tid={tenant}" if tenant else ""
    out: dict = {
        "tilejson": "2.2.0",
        "name": f"soil-{prop}-{depth}",
        "scheme": "xyz",
        "tiles": [f"{_PUBLIC_PREFIX}/v1/soil/tiles/{prop}/{depth}/{{z}}/{{x}}/{{y}}.png{tid_q}"],
        "minzoom": 6,
        "maxzoom": 15,
        "bounds": [-180.0, -85.0, 180.0, 85.0],
        "available": available,
        "property": prop,
        "name_ar": meta["name_ar"],
        "unit": meta["unit"],
        "depth": depth,
        "legend": _soil.soil_legend(prop),
        "disclaimer": _soil.DISCLAIMER_AR,
    }
    if not available:
        out["reason"] = (
            "soilgrids-source-not-configured"
            if not _soil.is_source_configured()
            else "layer-file-missing"
        )
        out["user_message"] = (
            "طبقة التربة (SoilGrids) غير مُهيّأة: اضبط SOILGRIDS_DIR إلى مجلّد GeoTIFF "
            "(ملفّات باسم <property>_<depth>.tif) في بيئة خدمة الراستر ثمّ أعِد التشغيل."
        )
    return out


@router.get("/v1/soil/properties")
async def soil_properties():
    """الخصائص/الأعماق المدعومة + حالة المصدر الصادقة (مُعلَن مقابل قابل للقراءة) + التحذير."""
    readable = _soil.readable_layer_count()
    return {
        "properties": _soil.supported_properties(),
        "depths": list(_soil.SOIL_DEPTHS),
        # صدق: مُعلَن (env مضبوط) قد يختلف عن قابل للقراءة (ملفّ موجود). نكشف الاثنين.
        "source_declared": _soil.is_source_configured(),
        "source_readable": readable > 0,
        "readable_layers": readable,
        # source_configured يعني الآن «قابل للخدمة فعلاً» لا مجرّد إعلان (لا تضليل).
        "source_configured": readable > 0,
        "disclaimer": _soil.DISCLAIMER_AR,
    }


def _parse_bbox(bbox) -> list[float] | None:
    if not isinstance(bbox, str) or not bbox:
        return None
    try:
        parts = [float(v) for v in bbox.split(",")]
        return parts if len(parts) == 4 else None
    except (TypeError, ValueError):
        return None


def _parse_poly_points(poly) -> list | None:
    """``poly="lng,lat;lng,lat;..."`` (EPSG:4326) ⇒ قائمة [lng,lat] للقصّ على حدّ الحقل، أو None."""
    if not isinstance(poly, str) or not poly:
        return None
    pts: list[list[float]] = []
    for pair in poly.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        try:
            lng_s, lat_s = pair.split(",")
            pts.append([float(lng_s), float(lat_s)])
        except (TypeError, ValueError):
            return None
    return pts if len(pts) >= 3 else None


@router.get("/v1/fields/{field_id}/soil/summary")
async def field_soil_summary(
    field_id: str,
    bbox: Annotated[
        str | None, Query(description="minLon,minLat,maxLon,maxLat (EPSG:4326)")
    ] = None,
    depth: Annotated[str, Query()] = "0-5cm",
    poly: Annotated[str | None, Query(description="lng,lat;... قصّ على حدّ الحقل")] = None,
):
    """ملخّص خصائص تربة الحقل (متوسّطات SoilGrids على **مضلّع الحقل** إن مُرِّر، وإلّا bbox) +
    صنف القوام — tenant-scoped.

    صدق: بلا مصدر/bbox ⇒ ``computed:false`` + سبب — لا تلفيق. توجيه لاختيار العيّنات.
    """
    await require_field_tenant(
        field_id, hide_existence=True, layers=LAYERS, field_layers=FIELD_LAYERS, logger=logger
    )
    result = _soil.compute_field_soil_summary(_parse_bbox(bbox), depth, _parse_poly_points(poly))
    result["field_id"] = field_id
    return result


@router.get("/v1/fields/{field_id}/soil/sampling-zones.geojson")
async def field_soil_sampling_zones(
    field_id: str,
    bbox: Annotated[
        str | None, Query(description="minLon,minLat,maxLon,maxLat (EPSG:4326)")
    ] = None,
    depth: Annotated[str, Query()] = "0-5cm",
    zones: Annotated[int, Query(ge=2, le=5)] = 3,
    poly: Annotated[str | None, Query(description="lng,lat;... قصّ على حدّ الحقل")] = None,
):
    """مناطق تربة متجانسة (GeoJSON) لتقسيم أخذ العيّنات — مقصوصة على **مضلّع الحقل** (poly)،
    tenant-scoped.

    صدق: بلا مصدر ⇒ ``features:[]`` + ``computed:false`` — لا تلفيق مناطق.
    """
    await require_field_tenant(
        field_id, hide_existence=True, layers=LAYERS, field_layers=FIELD_LAYERS, logger=logger
    )
    import soil_zones as _sz

    result = _sz.compute_soil_sampling_zones(
        _parse_bbox(bbox), depth, zones, _parse_poly_points(poly)
    )
    result["field_id"] = field_id
    return result


@router.get("/v1/fields/{field_id}/soil/sampling-plan")
async def field_soil_sampling_plan(
    field_id: str,
    bbox: Annotated[
        str | None, Query(description="minLon,minLat,maxLon,maxLat (EPSG:4326)")
    ] = None,
    depth: Annotated[str, Query()] = "0-5cm",
    zones: Annotated[int, Query(ge=2, le=5)] = 3,
    samples_per_zone: Annotated[int, Query(ge=1, le=3)] = 1,
    poly: Annotated[str | None, Query(description="lng,lat;... قصّ على حدّ الحقل")] = None,
):
    """نقاط عيّنات تربة تمثيليّة (GeoJSON Point) داخل **مضلّع الحقل** من مناطق k-means —
    tenant-scoped.

    صدق: بلا مصدر ⇒ ``features:[]`` + ``computed:false`` — لا نقاط مُلفَّقة.
    """
    await require_field_tenant(
        field_id, hide_existence=True, layers=LAYERS, field_layers=FIELD_LAYERS, logger=logger
    )
    import soil_zones as _sz

    result = _sz.compute_soil_sampling_points(
        _parse_bbox(bbox), depth, zones, samples_per_zone, _parse_poly_points(poly)
    )
    result["field_id"] = field_id
    return result
