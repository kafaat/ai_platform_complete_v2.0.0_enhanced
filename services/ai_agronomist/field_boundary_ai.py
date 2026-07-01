"""Field Boundary AI (V59) — deterministic proposal engine for agent tools.

This module intentionally does **not** persist geometry. It proposes candidate field
boundaries from a bbox/scene context and requires a separate high-risk write action to
save anything. The first implementation is a deterministic fallback contract that can be
replaced by SAM/U-Net/Sen2Agri later without changing the tool schema.
"""

from __future__ import annotations

import math
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

    Backend (V59.1): resolved through a replaceable adapter chain (best-first):
    ``registered_boundary_lookup → ftw_boundary_adapter → sentinel2_boundary_fallback
    → bbox_fallback``. FTW is used whenever a real model is available (env-gated); any
    absence/failure fails safe to the next adapter. Every result is a **proposal** with
    a 7-signal quality block; a guard flags degradation to bbox while imagery exists.
    The tool contract and return shape are stable regardless of the winning adapter.
    """
    from .field_boundary_backends import run_boundary_adapters

    source = str(params.get("source") or "truecolor").strip().lower()
    if source not in {"truecolor", "ndvi", "falsecolor"}:
        source = "truecolor"

    if normalize_bbox(params.get("bbox")) is None and not (imagery_context or {}).get(
        "registered_boundary"
    ):
        # لا bbox صالح ولا حدّ مسجَّل ⇒ لا مقترح (fail-closed).
        return {
            "field_id": field_id,
            "source": source,
            "proposed_boundaries": [],
            "requires_user_confirmation": True,
            "error": "invalid_bbox",
            "method": "deterministic_bbox_fallback",
        }

    adapter_out = run_boundary_adapters(params, imagery_context)
    if adapter_out is None:  # لا محوّل أنتج هندسة ⇒ fail-closed.
        return {
            "field_id": field_id,
            "source": source,
            "proposed_boundaries": [],
            "requires_user_confirmation": True,
            "error": "invalid_bbox",
            "method": "deterministic_bbox_fallback",
        }

    winner = adapter_out["winner"]
    proposed = [
        {
            "geometry": p["geometry"],
            "confidence": winner["confidence"],
            "area_ha": p.get("area_ha"),
            "method": p.get("method", "adapter_polygon"),
        }
        for p in winner["proposals"]
    ]
    return {
        "field_id": field_id,
        "source": source,
        "date": params.get("date"),
        "crop_hint": params.get("crop_hint"),
        "boundary_source": adapter_out["boundary_source"],
        "adapters_tried": adapter_out["adapters_tried"],
        "quality": adapter_out["quality"],
        "degraded_to_bbox_despite_imagery": adapter_out["degraded_to_bbox_despite_imagery"],
        "method": "truecolor_edge_segmentation_fallback"
        if source == "truecolor"
        else "index_contour_fallback",
        "proposed_boundaries": proposed,
        "requires_user_confirmation": True,
        "persistence": "proposal_only_until_user_confirms",
    }
