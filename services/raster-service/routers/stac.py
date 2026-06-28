"""routers/stac.py — واجهة STAC الداخليّة وMosaicJSON (STAC Facade)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``main.py``.
"""

from __future__ import annotations

from fastapi import APIRouter

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
