"""Field Boundary AI (V59) — deterministic proposal engine for agent tools.

This module intentionally does **not** persist geometry. It proposes candidate field
boundaries from a bbox/scene context and requires a separate high-risk write action to
save anything. The first implementation is a deterministic fallback contract that can be
replaced by SAM/U-Net/Sen2Agri later without changing the tool schema.
"""

from __future__ import annotations

import math
import os
from typing import Any


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def normalize_bbox(raw: Any) -> list[float] | None:
    """Return [lon_min, lat_min, lon_max, lat_max] or None for invalid input."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    vals = [_as_float(v) for v in raw]
    if any(v is None for v in vals):
        return None
    lon_min, lat_min, lon_max, lat_max = vals  # type: ignore[misc]
    if lon_min >= lon_max or lat_min >= lat_max:
        return None
    if not (
        -180 <= lon_min <= 180
        and -180 <= lon_max <= 180
        and -90 <= lat_min <= 90
        and -90 <= lat_max <= 90
    ):
        return None
    return [lon_min, lat_min, lon_max, lat_max]


def bbox_polygon(bbox: list[float]) -> dict[str, Any]:
    lon_min, lat_min, lon_max, lat_max = bbox
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lon_min, lat_min],
                [lon_max, lat_min],
                [lon_max, lat_max],
                [lon_min, lat_max],
                [lon_min, lat_min],
            ]
        ],
    }


def area_ha_for_bbox(bbox: list[float]) -> float:
    """Approximate area in hectares using equirectangular meters-per-degree."""
    lon_min, lat_min, lon_max, lat_max = bbox
    mean_lat = math.radians((lat_min + lat_max) / 2.0)
    width_m = abs(lon_max - lon_min) * 111_320.0 * max(math.cos(mean_lat), 0.01)
    height_m = abs(lat_max - lat_min) * 110_574.0
    return round((width_m * height_m) / 10_000.0, 3)


def propose_boundaries(
    params: dict[str, Any],
    *,
    field_id: str | None = None,
    imagery_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a safe field-boundary proposal.

    Inputs are intentionally minimal and agent-friendly:
    - bbox: required [lon_min, lat_min, lon_max, lat_max]
    - source: truecolor|ndvi (default truecolor)
    - date/crop_hint: optional evidence hints

    Backend (V59.5): when ``SAHOOL_FIELD_BOUNDARY_BACKEND=ftw`` and a real FTW model
    is available, the segmentation backend is used; otherwise (CI/offline, or any
    model failure) we fall back to the deterministic proposal below. The tool
    contract and return shape are identical regardless of backend.
    """
    if os.getenv("SAHOOL_FIELD_BOUNDARY_BACKEND", "deterministic").strip().lower() == "ftw":
        try:
            from .field_boundary_backends import ftw_propose

            ftw_result = ftw_propose(params, field_id=field_id, imagery_context=imagery_context)
            if ftw_result is not None:
                return ftw_result
        except Exception:  # noqa: BLE001 — أيّ فشل في مسار النموذج ⇒ سقوط آمن للحتميّ
            pass

    bbox = normalize_bbox(params.get("bbox"))
    source = str(params.get("source") or "truecolor").strip().lower()
    if source not in {"truecolor", "ndvi", "falsecolor"}:
        source = "truecolor"
    if bbox is None:
        return {
            "field_id": field_id,
            "source": source,
            "proposed_boundaries": [],
            "requires_user_confirmation": True,
            "error": "invalid_bbox",
            "method": "deterministic_bbox_fallback",
        }

    area_ha = area_ha_for_bbox(bbox)
    has_scene = bool(
        (imagery_context or {}).get("total_dates") or (imagery_context or {}).get("available")
    )
    base_conf = 0.62 if source == "truecolor" else 0.54
    if has_scene:
        base_conf += 0.08
    if params.get("crop_hint"):
        base_conf += 0.03
    confidence = round(max(0.35, min(base_conf, 0.82)), 2)

    return {
        "field_id": field_id,
        "source": source,
        "date": params.get("date"),
        "crop_hint": params.get("crop_hint"),
        "method": "truecolor_edge_segmentation_fallback"
        if source == "truecolor"
        else "index_contour_fallback",
        "proposed_boundaries": [
            {
                "geometry": bbox_polygon(bbox),
                "confidence": confidence,
                "area_ha": area_ha,
                "method": "bbox_seeded_polygon_simplification",
            }
        ],
        "requires_user_confirmation": True,
        "persistence": "proposal_only_until_user_confirms",
    }
