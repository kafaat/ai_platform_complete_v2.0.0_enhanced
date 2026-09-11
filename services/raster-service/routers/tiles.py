"""routers/tiles.py — بلاطات الطبقات وtilejson الثابت (Layer Tiles)."""

from __future__ import annotations

import logging
import os
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from raster_runtime_state import LAYERS
from raster_security_context import (
    public_cog_url,
    require_layer_tenant,
    require_layer_tenant_authorized,
)
from raster_settings import TITILER_URL, TRANSPARENT_PNG, UPLOAD_DIR

from shared.gis.cog_tile_proxy import fetch_registered_cog_tile

logger = logging.getLogger("raster-service")
router = APIRouter()


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
    cog_url = public_cog_url(layer.get("cog_url") or layer.get("raster_url"))

    if TITILER_URL and cog_url:
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
        "note": "بلاطات ثابتة مُولَّدة مسبقاً (TiTiler غير مضبوط). للديناميكي: اضبط TITILER_URL ووفّر cog_url للطبقة.",
    }
