"""routers/tiles.py — بلاطات الطبقات وtilejson الثابت (Layer Tiles)."""

from __future__ import annotations

import logging
import os
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from raster_runtime_state import LAYERS
from raster_security_context import (
    dynamic_tile_refusal,
    public_cog_url,
    require_layer_tenant,
    require_layer_tenant_authorized,
)
from raster_settings import TITILER_URL, TRANSPARENT_PNG, UPLOAD_DIR

from shared.gis.cog_tile_proxy import fetch_registered_cog_tile

logger = logging.getLogger("raster-service")
router = APIRouter()

#: ملاحظةُ البديل الثابت تُسمّي المُدخَلَ الناقص فعلاً — كانت «TiTiler غير مضبوط. اضبط
#: TITILER_URL» في كلّ حالة، والمتغيّرُ مضبوطٌ في ``.env.example`` وافتراض v9.
_STATIC_NOTES = {
    "layer_has_no_public_cog": "بلاطات ثابتة مُولَّدة مسبقاً: لا مصدر COG عامّاً (https) لهذه الطبقة.",
    "titiler_url_not_configured": "بلاطات ثابتة مُولَّدة مسبقاً: TITILER_URL غير مضبوط.",
    "titiler_url_invalid": "بلاطات ثابتة مُولَّدة مسبقاً: TITILER_URL ليس رابط http(s) صالحاً.",
    "cog_tile_allowed_hosts_not_configured": (
        "بلاطات ثابتة مُولَّدة مسبقاً: COG_TILE_ALLOWED_HOSTS فارغ — لا مضيفَ COG موثوقاً للبلاطات الديناميكيّة."
    ),
    "cog_tile_source_not_allowed": (
        "بلاطات ثابتة مُولَّدة مسبقاً: مضيفُ COG هذه الطبقة ليس في COG_TILE_ALLOWED_HOSTS."
    ),
}


@router.get("/v1/tiles/{layer_id}/{z}/{x}/{y}.png")
async def get_tile(
    layer_id: str, z: int, x: int, y: int, colormap: str = "viridis", rescale: str | None = None
):
    """بلاطة خريطة لطبقة (MapLibre)."""
    require_layer_tenant(layer_id, layers=LAYERS)
    await require_layer_tenant_authorized(layer_id, layers=LAYERS, logger=logger)
    if layer_id not in LAYERS:
        raise HTTPException(404, "طبقة غير موجودة")
    tile_path = os.path.join(UPLOAD_DIR, layer_id, f"{z}_{x}_{y}.png")
    if os.path.exists(tile_path):
        with open(tile_path, "rb") as fh:
            return Response(content=fh.read(), media_type="image/png")
    layer = LAYERS[layer_id]
    cog_url = public_cog_url(layer.get("cog_url") or layer.get("raster_url"))
    if cog_url:
        content = await fetch_registered_cog_tile(
            cog_url, z, x, y, base_url=TITILER_URL, colormap=colormap, rescale=rescale
        )
        return Response(
            content, media_type="image/png", headers={"Cache-Control": "private, no-store"}
        )
    return Response(content=TRANSPARENT_PNG, media_type="image/png")


@router.get("/v1/layers/{layer_id}/tilejson")
async def layer_tilejson(
    layer_id: str, rescale: str | None = Query(None), colormap: str | None = Query("viridis")
):
    """يُرجِع قالب رابط البلاطات لـMapLibre."""
    require_layer_tenant(layer_id, layers=LAYERS)
    await require_layer_tenant_authorized(layer_id, layers=LAYERS, logger=logger)
    if layer_id not in LAYERS:
        raise HTTPException(404, "طبقة غير موجودة")
    layer = LAYERS[layer_id]
    # يُسأل كلُّ ما يسأله الناقل لا ``TITILER_URL`` وحدَه: بـ``.env.example`` كما هو
    # (خلفيّةٌ مضبوطة وقائمةُ مصادر فارغة) كان القالبُ الديناميكيّ يُعلَن وكلُّ بلاطةٍ 503.
    refusal = dynamic_tile_refusal(layer.get("cog_url") or layer.get("raster_url"), TITILER_URL)

    if refusal is None:
        options = {"colormap": colormap or "viridis"}
        if rescale:
            options["rescale"] = rescale
        params = urlencode(options)
        return {
            "source": "titiler-dynamic",
            "tilejson": "2.2.0",
            "tiles": [
                f"/api/raster/v1/tiles/{quote(layer_id, safe='')}/{{z}}/{{x}}/{{y}}.png?{params}"
            ],
            "minzoom": 8,
            "maxzoom": 18,
            "note": "بلاطات ديناميكيّة من COG عبر TiTiler (تمدّد/ألوان عند الطلب)",
        }
    return {
        "source": "static-pregenerated",
        "tilejson": "2.2.0",
        "tiles": [f"/api/raster/v1/tiles/{quote(layer_id, safe='')}/{{z}}/{{x}}/{{y}}.png"],
        "minzoom": 8,
        "maxzoom": 16,
        "dynamic_unavailable_reason": refusal,
        "note": _STATIC_NOTES.get(refusal, _STATIC_NOTES["layer_has_no_public_cog"]),
    }
