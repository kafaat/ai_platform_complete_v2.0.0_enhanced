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

import os

import main
import soil_render as _soil
from fastapi import APIRouter, Query, Response

router = APIRouter()

_PUBLIC_PREFIX = os.getenv("RASTER_PUBLIC_PREFIX", "/api/raster").rstrip("/")


def _tenant_ctx_ok() -> bool:
    return main._REQ_TENANT.get() is not None


@router.get("/v1/soil/tiles/{prop}/{depth}/{z}/{x}/{y}.png")
async def soil_tile(prop: str, depth: str, z: int, x: int, y: int, tid: str | None = Query(None)):
    """بلاطة خاصّيّة تربة ملوّنة. شفّافة عند غياب المصدر/السياق (fail-closed صادق)."""
    if not _tenant_ctx_ok():
        return Response(content=main._TRANSPARENT_PNG, media_type="image/png")
    png = _soil.render_soil_tile(prop, _soil.normalize_depth(depth), z, x, y)
    return Response(
        content=png or main._TRANSPARENT_PNG,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/v1/soil/tilejson")
async def soil_tilejson(property: str = Query("phh2o"), depth: str = Query("0-5cm")):
    """TileJSON لطبقة خاصّيّة تربة — يستهلكه Leaflet/MapLibre.

    ``available`` يعكس تهيئة المصدر لهذه (الخاصّيّة، العمق) فعليّاً. ``disclaimer`` إلزاميّ
    دائماً (الطبقة توجيهيّة لا بديلة عن المختبر).
    """
    prop = property if property in _soil.SOIL_PROPERTIES else "phh2o"
    depth = _soil.normalize_depth(depth)
    meta = _soil.SOIL_PROPERTIES[prop]
    available = _soil.soil_raster_path(prop, depth) is not None
    tenant = main._REQ_TENANT.get()
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
    """الخصائص/الأعماق المدعومة + هل مصدر SoilGrids مُهيّأ (للواجهة) + التحذير الإلزاميّ."""
    return {
        "properties": _soil.supported_properties(),
        "depths": list(_soil.SOIL_DEPTHS),
        "source_configured": _soil.is_source_configured(),
        "disclaimer": _soil.DISCLAIMER_AR,
    }


def _parse_bbox(bbox: str | None) -> list[float] | None:
    if not bbox:
        return None
    try:
        parts = [float(v) for v in bbox.split(",")]
        return parts if len(parts) == 4 else None
    except (TypeError, ValueError):
        return None


@router.get("/v1/fields/{field_id}/soil/summary")
async def field_soil_summary(
    field_id: str,
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat (EPSG:4326)"),
    depth: str = Query("0-5cm"),
):
    """ملخّص خصائص تربة الحقل (متوسّطات SoilGrids على bbox) + صنف القوام — tenant-scoped.

    صدق: بلا مصدر/bbox ⇒ ``computed:false`` + سبب — لا تلفيق. توجيه لاختيار العيّنات.
    """
    await main._require_field_tenant(field_id, hide_existence=True)
    result = _soil.compute_field_soil_summary(_parse_bbox(bbox), depth)
    result["field_id"] = field_id
    return result


@router.get("/v1/fields/{field_id}/soil/sampling-zones.geojson")
async def field_soil_sampling_zones(
    field_id: str,
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat (EPSG:4326)"),
    depth: str = Query("0-5cm"),
    zones: int = Query(3, ge=2, le=5),
):
    """مناطق تربة متجانسة (GeoJSON) لتقسيم أخذ العيّنات — tenant-scoped.

    صدق: بلا مصدر ⇒ ``features:[]`` + ``computed:false`` — لا تلفيق مناطق.
    """
    await main._require_field_tenant(field_id, hide_existence=True)
    import soil_zones as _sz

    result = _sz.compute_soil_sampling_zones(_parse_bbox(bbox), depth, zones)
    result["field_id"] = field_id
    return result


@router.get("/v1/fields/{field_id}/soil/sampling-plan")
async def field_soil_sampling_plan(
    field_id: str,
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat (EPSG:4326)"),
    depth: str = Query("0-5cm"),
    zones: int = Query(3, ge=2, le=5),
    samples_per_zone: int = Query(1, ge=1, le=3),
):
    """نقاط عيّنات تربة تمثيليّة (GeoJSON Point) من مراكز مناطق k-means — tenant-scoped.

    صدق: بلا مصدر ⇒ ``features:[]`` + ``computed:false`` — لا نقاط مُلفَّقة.
    """
    await main._require_field_tenant(field_id, hide_existence=True)
    import soil_zones as _sz

    result = _sz.compute_soil_sampling_points(_parse_bbox(bbox), depth, zones, samples_per_zone)
    result["field_id"] = field_id
    return result
