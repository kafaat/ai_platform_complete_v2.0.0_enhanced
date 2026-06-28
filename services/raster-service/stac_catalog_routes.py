"""مسارات واجهة STAC/الكتالوج السحابيّ لخدمة الراستر (Phase 4).

شريحة متماسكة محفوظة-السلوك مُستخرَجة من ``main.py`` (المرحلة 3): نقاط واجهة
الكتالوج السحابيّ (STAC facade) — صفحة STAC الجذر، المجموعات، MosaicJSON،
تقييم جودة المشهد، ومعاينة سجلّ COG. كلّها عامّة (PUBLIC_CATALOG): لا تقرأ
بيانات مستأجِر ولا حالة على مستوى الوحدة في ``main.py``؛ تفوّض كلّيّاً إلى
``cloud_native_catalog`` (الذي لا يعتمد على rasterio/GDAL) فتُعزَل بأمان.

العقد ثابت تماماً: نفس المسارات/الأساليب/الأسماء/السلوك. يُضَمّ هذا الراوتر في
``main.py`` عبر ``app.include_router(...)`` بلا بادئة (prefix) فتبقى المسارات
كما هي حرفيّاً. حارس تصنيف نقاط الراستر يقرأ هذه الوحدة بالإضافة إلى ``main.py``
(يحرس العقد لا الموضع).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/stac")
async def stac_landing() -> dict:
    """STAC landing page for SAHOOL internal imagery catalog facade."""
    import cloud_native_catalog as _cnc

    return _cnc.stac_landing_page()


@router.get("/stac/collections")
async def stac_collections() -> dict:
    """List internal STAC collections: source scenes and derived COG products."""
    import cloud_native_catalog as _cnc

    return _cnc.stac_collections()


@router.post("/stac/mosaicjson")
async def stac_mosaicjson(payload: dict) -> dict:
    """Build a lightweight MosaicJSON document from supplied STAC items/COG assets.

    This endpoint is intentionally stateless: persistence belongs to raster_registry/object
    storage. It lets the frontend/tiler preview a multi-scene mosaic contract safely.
    """
    import cloud_native_catalog as _cnc

    return _cnc.build_mosaicjson(
        name=str(payload.get("name") or "sahool-field-mosaic"),
        items=payload.get("items") or [],
        minzoom=int(payload.get("minzoom") or 8),
        maxzoom=int(payload.get("maxzoom") or 18),
    )


@router.post("/v1/scenes/quality-score")
async def scene_quality_score(payload: dict) -> dict:
    """Score scene quality from cloud/shadow/nodata metadata before processing."""
    import cloud_native_catalog as _cnc

    q = _cnc.score_scene_quality(
        cloud_pct=payload.get("cloud_pct"),
        shadow_pct=payload.get("shadow_pct", 0),
        nodata_pct=payload.get("nodata_pct", 0),
        haze_pct=payload.get("haze_pct", 0),
        resolution_m=payload.get("resolution_m", 10),
        max_cloud_pct=float(payload.get("max_cloud_pct", 35)),
    )
    return q.__dict__


@router.post("/v1/cog/registry/preview")
async def cog_registry_preview(payload: dict) -> dict:
    """Preview the canonical COG registry record without writing to DB."""
    import cloud_native_catalog as _cnc

    required = ["tenant_id", "field_id", "date", "index_type", "cog_url"]
    missing = [k for k in required if not payload.get(k)]
    if missing:
        raise HTTPException(status_code=422, detail={"missing": missing})
    return _cnc.cog_registry_record(
        tenant_id=str(payload["tenant_id"]),
        field_id=str(payload["field_id"]),
        date=str(payload["date"]),
        index_type=str(payload["index_type"]),
        cog_url=str(payload["cog_url"]),
        scene_id=payload.get("scene_id"),
        cloud_pct=payload.get("cloud_pct"),
        resolution_m=payload.get("resolution_m", 10),
    )
