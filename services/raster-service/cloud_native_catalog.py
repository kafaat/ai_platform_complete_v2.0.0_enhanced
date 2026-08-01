"""Cloud-native raster/catalog utilities for raster-service.

لا يعتمد على rasterio/GDAL كي يبقى قابلاً للاختبار داخل CI الخفيف. الوظائف هنا
تغطي عقود STAC/TiTiler/Terracotta/s2cloudless: Registry, MosaicJSON, جودة مشهد.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from shared.gis.cloud_native_gis import (
        build_mosaicjson,
        normalize_stac_item,
        score_scene_quality,
    )
except Exception:  # pragma: no cover - عند تشغيل الخدمة من مجلدها مباشرة
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from shared.gis.cloud_native_gis import (
        build_mosaicjson,
        normalize_stac_item,
        score_scene_quality,
    )


def stac_landing_page(base_url: str = "") -> dict[str, Any]:
    base = base_url.rstrip("/")
    return {
        "type": "Catalog",
        "id": "sahool-raster-catalog",
        "stac_version": "1.0.0",
        "description": "SAHOOL internal STAC facade for field imagery, COG registry and mosaics.",
        "links": [
            {"rel": "self", "href": f"{base}/v1/stac" if base else "/v1/stac"},
            {
                "rel": "search",
                "href": f"{base}/v1/stac/search" if base else "/v1/stac/search",
                "method": "POST",
            },
            {
                "rel": "data",
                "href": f"{base}/v1/stac/collections" if base else "/v1/stac/collections",
            },
        ],
    }


def stac_collections() -> dict[str, Any]:
    return {
        "collections": [
            {
                "id": "sentinel-2-l2a",
                "title": "Sentinel-2 L2A field scenes",
                "description": "Cloud-masked optical imagery used for NDVI/truecolor and stress analytics.",
                "license": "proprietary",
                "extent": {
                    "spatial": {"bbox": [[-180, -90, 180, 90]]},
                    "temporal": {"interval": [[None, None]]},
                },
            },
            {
                "id": "field-cog-products",
                "title": "SAHOOL COG products",
                "description": "Derived COGs and raster indicators indexed by tenant/field/date/index.",
                "license": "proprietary",
                "extent": {
                    "spatial": {"bbox": [[-180, -90, 180, 90]]},
                    "temporal": {"interval": [[None, None]]},
                },
            },
        ]
    }


def cog_registry_record(
    *,
    tenant_id: str,
    field_id: str,
    date: str,
    index_type: str,
    cog_url: str,
    scene_id: str | None = None,
    cloud_pct: float | None = None,
    resolution_m: float | None = 10,
) -> dict[str, Any]:
    quality = score_scene_quality(cloud_pct=cloud_pct or 0, resolution_m=resolution_m)
    return {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "date": date,
        "index_type": index_type,
        "cog_url": cog_url,
        "scene_id": scene_id,
        "cloud_pct": float(cloud_pct or 0),
        "resolution_m": float(resolution_m or 10),
        "quality": quality.__dict__,
        "tilejson_url": f"/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}?url={cog_url}",
    }


__all__ = [
    "build_mosaicjson",
    "normalize_stac_item",
    "score_scene_quality",
    "stac_landing_page",
    "stac_collections",
    "cog_registry_record",
]
