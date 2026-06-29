"""routers/tiles.py — بلاطات الطبقات وtilejson الثابت (Layer Tiles)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المنطق مطابقة.
التبعيّات المشتركة (الحالة/المساعِدات/النماذج) تبقى في ``main`` وتُشار إليها عبر
``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix في نهاية ``main.py``.
"""

from __future__ import annotations

import os

import main
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter()


@router.get("/tiles/{layer_id}/{z}/{x}/{y}.png")
async def get_tile(layer_id: str, z: int, x: int, y: int):
    """بلاطة خريطة لطبقة (MapLibre). عند توفّر البلاطات المُنتجة تُخدَم من
    القرص؛ وإلّا تُرجع بلاطة شفّافة (بنية صحيحة للعرض)."""
    main._require_layer_tenant(layer_id)  # تفويض: الطبقة تخصّ مستأجِر الطلب (إغلاق IDOR)
    await main._require_layer_tenant_authorized(layer_id)
    if layer_id not in main._layers:
        raise HTTPException(404, "طبقة غير موجودة")
    tile_path = os.path.join(main.UPLOAD_DIR, layer_id, f"{z}_{x}_{y}.png")
    if os.path.exists(tile_path):
        with open(tile_path, "rb") as fh:
            return Response(content=fh.read(), media_type="image/png")
    return Response(content=main._TRANSPARENT_PNG, media_type="image/png")


@router.get("/layers/{layer_id}/tilejson")
async def layer_tilejson(
    layer_id: str, rescale: str | None = Query(None), colormap: str | None = Query("viridis")
):
    """يُرجِع قالب رابط البلاطات لـMapLibre (سدّ فجوة P0).

    إن ضُبط TITILER_URL ووُجد COG للطبقة → رابط TiTiler ديناميكي (تمدّد ألوان
    وخريطة ألوان عند الطلب، بلا إعادة توليد). وإلّا → البلاطات الثابتة fallback.
    صدق: لا يدّعي ديناميكيّة غير متوفّرة — يُبلّغ بالمصدر الفعلي.
    """
    main._require_layer_tenant(layer_id)  # تفويض: الطبقة تخصّ مستأجِر الطلب (إغلاق IDOR)
    await main._require_layer_tenant_authorized(layer_id)
    if layer_id not in main._layers:
        raise HTTPException(404, "طبقة غير موجودة")
    layer = main._layers[layer_id]
    # cog_url للعميل: عامّ http(s) فقط (لا تسريب مسارات داخليّة عبر titiler)
    cog_url = main._public_cog_url(layer.get("cog_url") or layer.get("raster_url"))

    if main.TITILER_URL and cog_url:
        # رابط TiTiler ديناميكي من COG. rescale مثل "0,1" لـNDVI.
        params = f"url={cog_url}&colormap_name={colormap}"
        if rescale:
            params += f"&rescale={rescale}"
        return {
            "source": "titiler-dynamic",
            "tilejson": "2.2.0",
            "tiles": [f"{main.TITILER_URL}/cog/tiles/{{z}}/{{x}}/{{y}}.png?{params}"],
            "minzoom": 8,
            "maxzoom": 18,
            "note": "بلاطات ديناميكيّة من COG عبر TiTiler (تمدّد/ألوان عند الطلب)",
        }
    # fallback: البلاطات الثابتة
    return {
        "source": "static-pregenerated",
        "tilejson": "2.2.0",
        "tiles": [f"/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png"],
        "minzoom": 8,
        "maxzoom": 16,
        "note": "بلاطات ثابتة مُولَّدة مسبقاً (TiTiler غير مضبوط). للديناميكي: "
        "اضبط TITILER_URL ووفّر cog_url للطبقة.",
    }
