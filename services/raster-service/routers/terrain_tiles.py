"""
routers/terrain_tiles.py — طبقات التضاريس الثلاث كنقاط خريطة مستقلّة.

توصية التصميم (لكلّ طبقة استعمالها):
  • Hillshade — بلاطة Raster رماديّة: GET /v1/elevation/hillshade/{z}/{x}/{y}.png
  • Slope     — بلاطة Raster مُصنّفة: GET /v1/slope/{z}/{x}/{y}.png
  • Contours  — خطوط Vector (GeoJSON): GET /v1/fields/{field_id}/contours.geojson
  • TileJSON موحّد للطبقتين النقطيّتين: GET /v1/terrain/tilejson?layer=hillshade|slope

صدق صارم: بلا ``FIELD_DEM_PATH`` مُهيّأ ⇒ بلاطة شفّافة / ``features: []`` +
``available:false``/``computed:false`` — لا تلفيق تضاريس. auth كبلاطات CDSE: ``tid``
في الرابط (``<img>`` بلا ترويسات) ⇒ سياق مستأجِر؛ بلا سياق ⇒ شفّاف (لا وصول مجهول).
"""

from __future__ import annotations

import os
from typing import Annotated

import main
import terrain_render as _tr
from fastapi import APIRouter, Query, Response

router = APIRouter()

_PUBLIC_PREFIX = os.getenv("RASTER_PUBLIC_PREFIX", "/api/raster").rstrip("/")


def _dem_path() -> str | None:
    p = os.getenv("FIELD_DEM_PATH") or None
    return p if (p and os.path.isfile(p)) else None


def _tenant_ctx_ok() -> bool:
    # نفس عقد بلاطات CDSE: tid في الرابط ⇒ _REQ_TENANT مضبوط عبر الوسيط. بلا سياق ⇒ رفض.
    return main._REQ_TENANT.get() is not None


@router.get("/v1/terrain/status")
async def terrain_status():
    """حالة تفعيل طبقات التضاريس (هل DEM مُهيّأ؟) — تستهلكها الواجهة لشارة صادقة مرّة واحدة.

    صدق: ``dem_configured:false`` + سبب حين لا ``FIELD_DEM_PATH`` — لا تلفيق تفعيل.
    """
    dem = os.getenv("FIELD_DEM_PATH") or None
    configured = bool(dem and os.path.isfile(dem))
    return {
        "dem_configured": configured,
        "layers": ["hillshade", "slope", "contours"],
        "reason": None if configured else "FIELD_DEM_PATH not configured",
        "user_message": None
        if configured
        else "طبقات التضاريس غير مفعّلة: لم يُضبَط FIELD_DEM_PATH (نموذج ارتفاع DEM).",
    }


@router.get("/v1/elevation/hillshade/{z}/{x}/{y}.png")
async def hillshade_tile(z: int, x: int, y: int, tid: Annotated[str | None, Query()] = None):
    """بلاطة Hillshade (شكل الأرض). شفّافة عند غياب DEM/السياق (fail-closed صادق)."""
    if not _tenant_ctx_ok():
        return Response(content=main._TRANSPARENT_PNG, media_type="image/png")
    dem = _dem_path()
    png = _tr.render_hillshade_tile(dem, z, x, y) if dem else None
    return Response(
        content=png or main._TRANSPARENT_PNG,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/v1/slope/{z}/{x}/{y}.png")
async def slope_tile(z: int, x: int, y: int, tid: Annotated[str | None, Query()] = None):
    """بلاطة Slope مُصنّفة بالألوان (الأهمّ زراعيّاً). شفّافة عند غياب DEM/السياق."""
    if not _tenant_ctx_ok():
        return Response(content=main._TRANSPARENT_PNG, media_type="image/png")
    dem = _dem_path()
    png = _tr.render_slope_tile(dem, z, x, y) if dem else None
    return Response(
        content=png or main._TRANSPARENT_PNG,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/v1/terrain/tilejson")
async def terrain_tilejson(layer: Annotated[str, Query()] = "hillshade"):
    """TileJSON للطبقة النقطيّة (hillshade|slope) — يستهلكه Leaflet/MapLibre.

    صدق: ``available`` يعكس تهيئة DEM فعليّاً؛ بلا DEM ⇒ ``available:false`` + سبب
    كي تُظهر الواجهة حالة «التضاريس غير مُهيّأة» بدل طبقة فارغة صامتة.
    """
    layer = "slope" if layer == "slope" else "hillshade"
    dem_configured = _dem_path() is not None
    tenant = main._REQ_TENANT.get()
    path = "slope" if layer == "slope" else "elevation/hillshade"
    tid_q = f"?tid={tenant}" if tenant else ""
    out: dict = {
        "tilejson": "2.2.0",
        "name": f"terrain-{layer}",
        "scheme": "xyz",
        "tiles": [f"{_PUBLIC_PREFIX}/v1/{path}/{{z}}/{{x}}/{{y}}.png{tid_q}"],
        "minzoom": 8,
        "maxzoom": 17,
        "bounds": [-180.0, -85.0, 180.0, 85.0],
        "available": dem_configured,
        "layer": layer,
    }
    if not dem_configured:
        out["reason"] = "dem-not-configured"
        out["user_message"] = (
            "نموذج الارتفاع (DEM) غير مُهيّأ: اضبط FIELD_DEM_PATH إلى ملفّ DEM "
            "(مثل Copernicus GLO‑30) في بيئة خدمة الراستر ثمّ أعِد التشغيل."
        )
    if layer == "slope":
        out["legend"] = _tr.slope_legend()
    return out


@router.get("/v1/fields/{field_id}/contours.geojson")
async def field_contours(
    field_id: str,
    bbox: Annotated[
        str | None, Query(description="minLon,minLat,maxLon,maxLat (EPSG:4326)")
    ] = None,
    interval_m: Annotated[float, Query(ge=1.0, le=500.0)] = 10.0,
):
    """خطوط كنتور الحقل (GeoJSON) من DEM مقصوصٍ على bbox — لتخطيط المدرّجات/الريّ.

    tenant-scoped كبقيّة نقاط الحقل. صدق: بلا DEM/bbox ⇒ ``features: []`` +
    ``computed:false`` بمصدره — لا كنتور مُلفَّق.
    """
    await main._require_field_tenant(field_id, hide_existence=True)
    parsed_bbox: list[float] | None = None
    if bbox:
        try:
            parts = [float(v) for v in bbox.split(",")]
            if len(parts) == 4:
                parsed_bbox = parts
        except (TypeError, ValueError):
            parsed_bbox = None
    result = _tr.compute_field_contours(_dem_path(), parsed_bbox, interval_m)
    result["field_id"] = field_id
    return result
