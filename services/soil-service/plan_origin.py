"""Soil-sampling plan copies and plan-point origin resolution (gap P6, owned by soil-service).

The AI planner's plans reach soil-service as copies (``soil_sampling_plan_copies``, v273). A lab
sample that names a plan point is resolved here, from the stored copy, never from the planned
position, zone or imagery the client sends with the sample:

* an unknown plan id, or a plan of another tenant or field, is refused (``sampling_plan_not_found``);
* a point id that is not in the stored plan is refused (``sampling_point_not_in_plan``);
* a collection position farther from the planned point than the tolerance is refused
  (``sampling_origin_out_of_tolerance``) unless the collector states why (``deviation_reason``);
  the distance is measured and recorded either way.

The tolerance is ``ON_PLAN_TOLERANCE_M`` plus the reported GPS accuracy, and the GPS allowance is
capped at ``MAX_GPS_ALLOWANCE_M``: an accuracy the client reports is not allowed to widen the
tolerance to any distance it likes.

Pure functions only; persistence is in ``plan_copy_store``.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

ON_PLAN_TOLERANCE_M = 30.0
MAX_GPS_ALLOWANCE_M = 30.0
MIN_DEVIATION_REASON_CHARS = 3
MAX_PLAN_POINTS = 500
_INDICATORS = frozenset({"ndvi", "ndmi", "reci", "msavi", "slope"})
_PURPOSES = frozenset({"fertility", "nitrate", "salinity", "orchard", "texture", "no_till"})


class OriginRefused(ValueError):
    """A plan-point origin that soil-service will not certify. ``code`` is the typed reason."""

    def __init__(self, code: str, status: int, **extra: Any) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, **self.extra}


def _finite(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _planned_position(point: Any) -> tuple[float, float] | None:
    """``(latitude, longitude)`` of a stored plan point, or ``None`` if it has no valid position."""
    if not isinstance(point, dict):
        return None
    coords = (
        (point.get("point") or {}).get("coordinates")
        if isinstance(point.get("point"), dict)
        else None
    )
    if not isinstance(coords, list) or len(coords) != 2 or not all(_finite(c) for c in coords):
        return None
    lon, lat = float(coords[0]), float(coords[1])
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lat, lon


def plan_digest(plan: dict[str, Any], sample_points: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        {"plan": plan, "sample_points": sample_points},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_plan_copy(item: Any, field_id: str) -> dict[str, Any] | None:
    """A storable copy of one planner result for ``field_id``, or ``None`` if it is not one.

    A copy needs a plan id (1-64 chars), the same field, and 1-500 points that each carry an id
    and a valid position. Anything else is skipped, so a malformed plan never becomes a stored
    plan that samples could be resolved against."""
    if not isinstance(item, dict) or item.get("field_id") != field_id:
        return None
    plan, points = item.get("plan"), item.get("sample_points")
    plan_id = plan.get("plan_id") if isinstance(plan, dict) else None
    if not isinstance(plan_id, str) or not plan_id.strip() or len(plan_id) > 64:
        return None
    if not isinstance(points, list) or not 0 < len(points) <= MAX_PLAN_POINTS:
        return None
    ids = [p.get("sample_id") if isinstance(p, dict) else None for p in points]
    if not all(isinstance(i, str) and 0 < len(i) <= 80 for i in ids) or len(set(ids)) != len(ids):
        return None
    if not all(_planned_position(p) is not None for p in points):
        return None
    return {
        "plan_id": plan_id,
        "field_id": field_id,
        "plan": plan,
        "sample_points": points,
        "plan_digest": plan_digest(plan, points),
    }


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (haversine, mean Earth radius)."""
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(math.sqrt(min(1.0, h)))


def tolerance_m(gps_accuracy_m: float | None) -> float:
    allowance = float(gps_accuracy_m) if _finite(gps_accuracy_m) and gps_accuracy_m > 0 else 0.0
    return ON_PLAN_TOLERANCE_M + min(allowance, MAX_GPS_ALLOWANCE_M)


def _stored_point(points: Any, point_id: str) -> dict[str, Any] | None:
    for point in points if isinstance(points, list) else []:
        if isinstance(point, dict) and point.get("sample_id") == point_id:
            return point if _planned_position(point) is not None else None
    return None


def _same(claimed: Any, stored: Any) -> bool:
    if _finite(claimed) and _finite(stored):
        return abs(float(claimed) - float(stored)) <= 1e-9
    return claimed == stored


def resolve_origin(
    *,
    plan_id: str,
    plan_digest_value: str,
    sample_points: Any,
    point_id: str,
    latitude: float,
    longitude: float,
    gps_accuracy_m: float | None,
    deviation_reason: str | None,
    claimed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The origin to record with a plan-point sample, resolved from the stored plan copy.

    Raises ``OriginRefused`` when the point is not in the plan, or when the collection position
    is beyond the tolerance and no deviation reason is given. Client claims that differ from the
    stored plan are listed in ``client_claim_mismatch`` and never recorded as the origin."""
    if not (_finite(latitude) and _finite(longitude)):
        raise OriginRefused("sampling_collection_position_invalid", 422)
    point = _stored_point(sample_points, point_id)
    if point is None:
        raise OriginRefused("sampling_point_not_in_plan", 422, plan_id=plan_id, point_id=point_id)
    planned_lat, planned_lon = _planned_position(point)
    depth = point.get("depth_cm")
    indicators = [i for i in point.get("indicators") or [] if i in _INDICATORS]
    sources = point.get("indicator_sources")
    origin: dict[str, Any] = {
        "point_id": point_id,
        "zone_id": point.get("zone_id") if isinstance(point.get("zone_id"), str) else None,
        "latitude": planned_lat,
        "longitude": planned_lon,
        "location_id": point.get("location_id")
        if isinstance(point.get("location_id"), str)
        else None,
        "composite": point.get("composite") if isinstance(point.get("composite"), bool) else None,
        "sampling_purpose": (
            point.get("sampling_purpose") if point.get("sampling_purpose") in _PURPOSES else None
        ),
        "planned_depth_cm": (
            [float(depth[0]), float(depth[1])]
            if isinstance(depth, list) and len(depth) == 2 and all(_finite(d) for d in depth)
            else None
        ),
        "indicators": indicators,
        "indicator_sources": (
            {k: v for k, v in sources.items() if k in indicators and isinstance(v, dict)}
            if isinstance(sources, dict)
            else {}
        ),
    }
    origin = {k: v for k, v in origin.items() if v is not None}
    claim = claimed if isinstance(claimed, dict) else {}
    mismatch = sorted(
        key
        for key in (
            "zone_id",
            "latitude",
            "longitude",
            "location_id",
            "sampling_purpose",
            "indicators",
            "indicator_sources",
        )
        if claim.get(key) not in (None, [], {}) and not _same(claim.get(key), origin.get(key))
    )
    deviation = distance_m(planned_lat, planned_lon, float(latitude), float(longitude))
    tolerance = tolerance_m(gps_accuracy_m)
    on_plan = deviation <= tolerance
    reason = deviation_reason.strip() if isinstance(deviation_reason, str) else ""
    if not on_plan and len(reason) < MIN_DEVIATION_REASON_CHARS:
        raise OriginRefused(
            "sampling_origin_out_of_tolerance",
            422,
            plan_id=plan_id,
            point_id=point_id,
            deviation_m=round(deviation, 1),
            tolerance_m=tolerance,
        )
    origin.update(
        plan_id=plan_id,
        plan_digest=plan_digest_value,
        verification="stored_plan",
        resolved_by="soil-service",
        client_claim_mismatch=mismatch,
        collection={
            "latitude": float(latitude),
            "longitude": float(longitude),
            "gps_accuracy_m": float(gps_accuracy_m) if _finite(gps_accuracy_m) else None,
            "deviation_m": round(deviation, 1),
            "tolerance_m": tolerance,
            "on_plan": on_plan,
            "deviation_reason": reason or None,
        },
    )
    return origin
