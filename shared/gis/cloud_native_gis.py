"""Cloud-native GIS helpers for SAHOOL Phase 4.

مستوحاة من أفضل ممارسات farmOS/farmOS-map وTiTiler/Terracotta وGeoParquet
وOGC API/STAC وs2cloudless، لكنها نقيّة ولا تعتمد على I/O كي يمكن اختبارها
واستخدامها في الخدمات والواجهة كعقد ثابت.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

_ALLOWED_REVISION_OPS = {
    "create",
    "edit",
    "split",
    "merge",
    "import",
    "auto_boundary",
    "rollback",
}


def _slug(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    text = re.sub(r"[^a-z0-9\u0600-\u06ff_-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "unknown"


# غطاء غيوم مجهول لا يُقرأ ٠٪: الدرجة لا تتجاوز أدنى B (لا A)، والمشهد لا يسبق
# مشهداً مقيساً أصفى منه. Unknown cloud cover is never "clear" (mirror of raster RS-01).
_UNKNOWN_CLOUD_SCORE_CAP = 70


def parse_cloud_cover_pct(value: Any) -> float | None:
    """Cloud cover percent in [0, 100], or ``None`` = unknown (never a fabricated 0).

    Mirror of raster-service ``scene_policy.parse_cloud_cover_pct``: absent, bool,
    unparsable, non-finite or out-of-range values are unknown, not clamped to 0.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(pct) or not 0.0 <= pct <= 100.0:
        return None
    return pct


@dataclass(frozen=True)
class SceneQuality:
    score: int
    grade: str
    accepted: bool
    limiting_factors: tuple[str, ...]
    cloud_known: bool = True


def score_scene_quality(
    *,
    cloud_pct: float | int | None,
    shadow_pct: float | int | None = 0,
    nodata_pct: float | int | None = 0,
    haze_pct: float | int | None = 0,
    resolution_m: float | int | None = 10,
    max_cloud_pct: float = 35,
) -> SceneQuality:
    """حوّل مخرجات s2cloudless/cloud-mask إلى درجة جودة 0..100 قابلة للترتيب.

    الدرجة محافظة: الغيوم/الظلال/النطاقات الفارغة تخصم من الثقة، والدقة الأسوأ من
    10م تخصم تدريجياً. accepted لا يعني أن الصورة مثالية؛ يعني صالحة للمعالجة
    التلقائية وفق سقف الغيوم.
    """
    cloud = parse_cloud_cover_pct(cloud_pct)
    shadow = max(0.0, min(100.0, float(shadow_pct or 0)))
    nodata = max(0.0, min(100.0, float(nodata_pct or 0)))
    haze = max(0.0, min(100.0, float(haze_pct or 0)))
    res = max(1.0, float(resolution_m or 10))

    score = 100.0
    score -= (cloud or 0.0) * 1.25
    score -= shadow * 0.75
    score -= nodata * 1.50
    score -= haze * 0.50
    if res > 10:
        score -= min(20.0, (res - 10.0) * 0.8)

    final = int(round(max(0.0, min(100.0, score))))
    factors: list[str] = []
    if cloud is None:
        # المجهول يبقى مجهولاً: لا خصم مختلَق ولا درجة A (G11).
        final = min(final, _UNKNOWN_CLOUD_SCORE_CAP)
        factors.append("cloud_pct_unknown")
    elif cloud > max_cloud_pct:
        factors.append("cloud_pct")
    if shadow > 15:
        factors.append("shadow_pct")
    if nodata > 5:
        factors.append("nodata_pct")
    if haze > 20:
        factors.append("haze_pct")
    if res > 20:
        factors.append("resolution_m")
    grade = "A" if final >= 85 else "B" if final >= 70 else "C" if final >= 50 else "D"
    return SceneQuality(
        score=final,
        grade=grade,
        # Unknown cover cannot be checked against the ceiling; platform policy
        # (cdse_client._apply_cloud_filter) admits it as unknown, flagged above.
        accepted=((cloud is None or cloud <= max_cloud_pct) and final >= 50),
        limiting_factors=tuple(factors),
        cloud_known=cloud is not None,
    )


def normalize_stac_item(item: dict[str, Any]) -> dict[str, Any]:
    """استخرج سجلاً داخلياً ثابتاً من STAC Item بدون افتراض مزوّد واحد."""
    props = item.get("properties") or {}
    assets = item.get("assets") or {}
    bbox = item.get("bbox") or props.get("bbox")
    raw_cloud = props.get("eo:cloud_cover")
    if raw_cloud is None:
        raw_cloud = props.get("cloud_cover")
    cloud = parse_cloud_cover_pct(raw_cloud)
    quality = score_scene_quality(cloud_pct=cloud)
    cog_assets = {
        name: asset.get("href")
        for name, asset in assets.items()
        if isinstance(asset, dict)
        and asset.get("href")
        and (
            "image/tiff" in str(asset.get("type", ""))
            or str(asset.get("href", "")).lower().endswith((".tif", ".tiff"))
        )
    }
    return {
        "scene_id": item.get("id"),
        "collection": item.get("collection"),
        "datetime": props.get("datetime") or props.get("start_datetime"),
        "bbox": bbox,
        "cloud_pct": cloud,  # None = unknown, never a fabricated 0%
        "quality": asdict(quality),
        "cog_assets": cog_assets,
        "asset_count": len(assets),
    }


def build_mosaicjson(
    *, name: str, items: Iterable[dict[str, Any]], minzoom: int = 8, maxzoom: int = 18
) -> dict[str, Any]:
    """أنشئ MosaicJSON مبسطاً يربط quadkey/scene-id بأصول COG.

    TiTiler يدعم MosaicJSON كنمط تجميع؛ هنا نحفظ عقداً مستقراً يمكن للـ registry
    أو الـ tiler أن يوسّعه لاحقاً إلى quadkeys فعلية.
    """
    tiles: dict[str, list[str]] = {}
    for raw in items:
        item = normalize_stac_item(raw)
        scene_id = item.get("scene_id") or f"scene-{len(tiles) + 1}"
        hrefs = [href for href in item.get("cog_assets", {}).values() if href]
        if hrefs:
            tiles[str(scene_id)] = hrefs
    return {
        "mosaicjson": "0.0.3",
        "name": name,
        "minzoom": int(minzoom),
        "maxzoom": int(maxzoom),
        "tiles": tiles,
        "asset_type": "cog",
    }


def geoparquet_partition_path(
    *, country: str, governorate: str, district: str, year: int, crop: str | None = None
) -> str:
    """مسار data-lake مستقر لتصدير GeoParquet حسب البلد/المحافظة/المديرية/السنة/المحصول."""
    parts = [
        f"country={_slug(country)}",
        f"governorate={_slug(governorate)}",
        f"district={_slug(district)}",
        f"year={int(year)}",
    ]
    if crop:
        parts.append(f"crop={_slug(crop)}")
    return "/".join(parts) + "/fields.geoparquet"


def geometry_revision_event(
    *,
    field_id: str,
    tenant_id: str,
    operation_type: str,
    geometry: dict[str, Any],
    changed_by: str | None = None,
    reason: str | None = None,
    source: str = "ui.map",
    parent_revision_id: int | None = None,
) -> dict[str, Any]:
    """بناء حدث ledger شبيه farmOS activity لكل تغيير هندسي قبل إدخاله في DB."""
    if operation_type not in _ALLOWED_REVISION_OPS:
        raise ValueError(f"unsupported geometry operation: {operation_type}")
    return {
        "field_id": field_id,
        "tenant_id": tenant_id,
        "operation_type": operation_type,
        "geometry": geometry,
        "changed_by": changed_by,
        "reason": reason,
        "source": source,
        "parent_revision_id": parent_revision_id,
        "changed_at": datetime.now(UTC).isoformat(),
    }


def ogc_collection_descriptor(
    *,
    collection_id: str,
    title: str,
    item_type: str,
    crs: str = "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
) -> dict[str, Any]:
    """وصف collection خفيف متوافق مع مبادئ OGC API Features/Tiles."""
    return {
        "id": collection_id,
        "title": title,
        "itemType": item_type,
        "crs": [crs],
        "links": [
            {"rel": "self", "href": f"/ogc/collections/{collection_id}"},
            {"rel": "items", "href": f"/ogc/collections/{collection_id}/items"},
        ],
    }
