"""Phase 6 precision agriculture intelligence.

This module is dependency-light by design so it can run in CI and as a fallback in
production when heavier geospatial/ML runtimes (SAM2, GeoSAM, rasterio, sklearn,
Dask/Ray) are unavailable.  The contracts are production-facing: AI boundary
extraction, management zones, prescription maps, yield stability, profitability
maps and a digital-twin snapshot.  Heavy model services can replace the fallback
implementations behind the same request/response shape.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from statistics import mean, pstdev
from typing import Any

from shared.precision_agriculture.nutrient_units import recipe_elemental_input

GeoJSON = dict[str, Any]


@dataclass(frozen=True)
class BoundaryExtractionResult:
    geometry: GeoJSON
    confidence: float
    area_ha: float
    method: str
    model: str
    warnings: list[str]
    topology: dict[str, Any]


@dataclass(frozen=True)
class ZoneFeature:
    id: str
    zone: int
    label: str
    score: float
    rate_multiplier: float
    properties: dict[str, Any]


@dataclass(frozen=True)
class PrescriptionFeature:
    id: str
    zone: int
    prescription_type: str
    crop: str
    rate: float
    unit: str
    properties: dict[str, Any]


@dataclass(frozen=True)
class YieldStabilityClass:
    zone: str
    label: str
    mean_yield: float
    cv: float
    trend: float
    years: int


@dataclass(frozen=True)
class ProfitabilityFeature:
    id: str
    zone: int
    gross_revenue_per_ha: float | None
    total_cost_per_ha: float
    profit_per_ha: float | None
    roi: float | None
    label: str
    # "ok" | "missing_yield": إنتاجيّة غائبة لا تُخترَع (كانت 3 ط/هـ صامتة).
    data_status: str = "ok"


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:12]}"


def _walk_coords(value: Any) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []

    def walk(v: Any) -> None:
        if isinstance(v, list) and len(v) >= 2 and all(isinstance(x, (int, float)) for x in v[:2]):
            coords.append((float(v[0]), float(v[1])))
        elif isinstance(v, list):
            for item in v:
                walk(item)

    walk(value)
    return coords


def geometry_bbox(geometry: GeoJSON) -> list[float]:
    coords = _walk_coords(geometry.get("coordinates"))
    if not coords:
        raise ValueError("geometry has no coordinates")
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return [min(xs), min(ys), max(xs), max(ys)]


def polygon_area_ha(geometry: GeoJSON) -> float:
    """Approximate area in hectares for lon/lat polygons.

    Uses an equirectangular approximation around the polygon centroid.  This is
    deterministic and good enough for validation/fallback; authoritative area
    should still use PostGIS geography or a projected CRS.
    """
    rings: list[list[list[float]]] = []
    gtype = geometry.get("type")
    if gtype == "Polygon":
        rings = geometry.get("coordinates", [])[:1]
    elif gtype == "MultiPolygon":
        rings = [poly[0] for poly in geometry.get("coordinates", []) if poly]
    else:
        return 0.0
    total_m2 = 0.0
    for ring in rings:
        if len(ring) < 4:
            continue
        lat0 = math.radians(sum(float(p[1]) for p in ring) / len(ring))
        meters_per_lon = 111_320.0 * math.cos(lat0)
        meters_per_lat = 110_540.0
        pts = [(float(x) * meters_per_lon, float(y) * meters_per_lat) for x, y, *_ in ring]
        shoelace = 0.0
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1], strict=False):
            shoelace += x1 * y2 - x2 * y1
        total_m2 += abs(shoelace) / 2.0
    return round(total_m2 / 10_000.0, 4)


def _bbox_polygon(bbox: list[float]) -> GeoJSON:
    minx, miny, maxx, maxy = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
    }


def _expand_bbox(bbox: list[float], pct: float) -> list[float]:
    minx, miny, maxx, maxy = bbox
    dx = max(maxx - minx, 1e-8) * pct
    dy = max(maxy - miny, 1e-8) * pct
    return [minx - dx, miny - dy, maxx + dx, maxy + dy]


def validate_topology(geometry: GeoJSON) -> dict[str, Any]:
    gtype = geometry.get("type")
    coords = _walk_coords(geometry.get("coordinates"))
    warnings: list[str] = []
    if gtype not in {"Polygon", "MultiPolygon"}:
        warnings.append("unsupported_geometry_type")
    if len(coords) < 4:
        warnings.append("too_few_vertices")
    bbox = geometry_bbox(geometry) if coords else None
    area_ha = polygon_area_ha(geometry) if coords else 0.0
    if area_ha <= 0:
        warnings.append("zero_or_negative_area")
    return {
        "valid": not warnings,
        "geometry_type": gtype,
        "vertex_count": len(coords),
        "bbox": bbox,
        "area_ha": area_ha,
        "warnings": warnings,
    }


def extract_boundary(
    *,
    field_id: str,
    seed_geometry: GeoJSON | None = None,
    imagery_id: str | None = None,
    imagery_bbox: list[float] | None = None,
    model: str = "sam2-geosam",
    simplify_tolerance_m: float = 2.0,
    human_review_required: bool = True,
) -> dict[str, Any]:
    """Extract or refine a field boundary.

    The fallback implementation preserves the seed geometry when available and
    generates a safe bbox polygon when only imagery bounds are available.  The
    response shape is ready for a heavier segmentation backend.
    """
    warnings: list[str] = []
    method = "seed_refinement_fallback"
    if seed_geometry:
        geometry = seed_geometry
    elif imagery_bbox:
        geometry = _bbox_polygon(_expand_bbox(imagery_bbox, -0.02))
        method = "imagery_bbox_fallback"
        warnings.append("seed_geometry_missing_used_imagery_bbox")
    else:
        raise ValueError("seed_geometry or imagery_bbox is required")

    topology = validate_topology(geometry)
    warnings.extend(topology.get("warnings", []))
    confidence = 0.78 if method == "seed_refinement_fallback" else 0.55
    if topology["valid"]:
        confidence += 0.12
    if imagery_id:
        confidence += 0.04
    if human_review_required:
        warnings.append("human_review_required_before_commit")
    confidence = round(max(0.0, min(0.96, confidence)), 2)
    result = BoundaryExtractionResult(
        geometry=geometry,
        confidence=confidence,
        area_ha=topology["area_ha"],
        method=method,
        model=model,
        warnings=warnings,
        topology=topology,
    )
    return {"field_id": field_id, "imagery_id": imagery_id, **asdict(result)}


def _finite_or_none(v: Any) -> float | None:
    """رقم منتهٍ أو None — الغياب يبقى غياباً (لا يصير 0 ولا قيمة افتراضيّة)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _require_nonnegative(v: Any, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        raise ValueError(f"{name} must be finite and nonnegative; got {v!r}")
    return float(v)


def _zone_rate_multiplier(z: dict[str, Any]) -> Any:
    """المُضاعِف الصريح (حتّى 0 = منطقة استثناء) وإلّا 1.0 — فحص ``is None`` لا ``or``."""
    raw = z.get("rate_multiplier")
    if raw is None:
        raw = (z.get("properties") or {}).get("rate_multiplier")
    return 1.0 if raw is None else raw


def _check_feature_units(samples: list[dict[str, Any]], keys: list[str]) -> dict[str, str | None]:
    """وحدة كلّ خاصّيّة من ``<key>_unit``؛ خلط وحدتين في خاصّيّة واحدة ⇒ ValueError."""
    units: dict[str, str | None] = {}
    for k in keys:
        seen = {str(s[f"{k}_unit"]) for s in samples if s.get(f"{k}_unit") is not None}
        if len(seen) > 1:
            raise ValueError(
                f"feature '{k}' mixes units {sorted(seen)}; convert to one unit before zoning"
            )
        units[k] = next(iter(seen)) if seen else None
    return units


def _feature_stats(
    samples: list[dict[str, Any]], keys: list[str]
) -> dict[str, tuple[float, float]]:
    stats: dict[str, tuple[float, float]] = {}
    for k in keys:
        vals = [v for v in (_finite_or_none(s.get(k)) for s in samples) if v is not None]
        if vals:
            stats[k] = (mean(vals), pstdev(vals))
    return stats


def _weighted_score(
    row: dict[str, Any],
    keys: list[str],
    weights: dict[str, float],
    stats: dict[str, tuple[float, float]],
) -> float | None:
    """درجة موزونة على قيم **مُطبَّعة** (z لكلّ خاصّيّة) — بلا تطبيع كان الارتفاع
    بالأمتار يطغى على NDVI (0..1). الخاصّيّة الغائبة تُستبعَد من البسط والمقام معاً؛
    عيّنة بلا أيّ خاصّيّة ⇒ None (غير مُصنَّفة، لا صفر مُختلَق)."""
    num = 0.0
    den = 0.0
    present = False
    for k in keys:
        v = _finite_or_none(row.get(k))
        if v is None or k not in stats:
            continue
        present = True
        mu, sd = stats[k]
        z = (v - mu) / sd if sd > 0 else 0.0
        w = weights.get(k, 1.0)
        num += z * w
        den += abs(w)
    if not present:
        return None
    return num / den if den else 0.0


def _safe_float(v: Any) -> float:
    try:
        f = float(v)
        return f if math.isfinite(f) else 0.0
    except Exception:
        return 0.0


def _quantile_cuts(values: list[float], n: int) -> list[float]:
    if not values:
        return []
    ordered = sorted(values)
    return [
        ordered[min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * i / n))))]
        for i in range(1, n)
    ]


def generate_management_zones(
    samples: list[dict[str, Any]],
    *,
    n_zones: int = 3,
    feature_keys: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    if n_zones < 2 or n_zones > 7:
        raise ValueError("n_zones must be between 2 and 7")
    if not samples:
        return {"zones": [], "features": [], "error": "no_samples"}
    feature_keys = (
        feature_keys
        or [
            k
            for k in ["ndvi", "ndre", "soil_ec", "elevation", "slope", "yield"]
            if any(k in s for s in samples)
        ]
        or ["value"]
    )
    weights = weights or {
        "ndvi": 1.8,
        "ndre": 1.4,
        "yield": 2.0,
        "soil_ec": -0.8,
        "slope": -0.4,
        "elevation": 0.2,
        "value": 1.0,
    }
    feature_units = _check_feature_units(samples, feature_keys)
    stats = _feature_stats(samples, feature_keys)
    scored: list[tuple[dict[str, Any], float]] = []
    unscored_ids: list[str] = []
    for s in samples:
        score = _weighted_score(s, feature_keys, weights, stats)
        if score is None:
            unscored_ids.append(str(s.get("id") or _stable_id(s, "zone")))
        else:
            scored.append((s, score))
    if not scored:
        return {
            "zones": [],
            "features": [],
            "error": "no_scorable_samples",
            "unscored_sample_ids": unscored_ids,
        }
    cuts = _quantile_cuts([score for _, score in scored], n_zones)
    labels3 = {0: "stress", 1: "medium", 2: "high_potential"}
    zone_features: list[ZoneFeature] = []
    counts = [0] * n_zones
    sums = [0.0] * n_zones
    for sample, score in scored:
        zone = min(sum(1 for c in cuts if score >= c), n_zones - 1)
        counts[zone] += 1
        sums[zone] += score
        label = labels3.get(zone, f"zone_{zone + 1}") if n_zones == 3 else f"zone_{zone + 1}"
        multiplier = round(0.75 + (zone / max(1, n_zones - 1)) * 0.5, 2)
        zone_features.append(
            ZoneFeature(
                id=str(sample.get("id") or _stable_id(sample, "zone")),
                zone=zone + 1,
                label=label,
                score=round(score, 4),
                rate_multiplier=multiplier,
                properties={k: sample.get(k) for k in sample.keys() if k != "geometry"},
            )
        )
    zones = []
    for i in range(n_zones):
        label = labels3.get(i, f"zone_{i + 1}") if n_zones == 3 else f"zone_{i + 1}"
        zones.append(
            {
                "zone": i + 1,
                "label": label,
                "sample_count": counts[i],
                "pct": round(100 * counts[i] / len(scored), 1),
                "mean_score": round(sums[i] / counts[i], 4) if counts[i] else None,
                "rate_multiplier": round(0.75 + (i / max(1, n_zones - 1)) * 0.5, 2),
            }
        )
    return {
        "algorithm": "weighted_quantile_fallback",
        "normalization": "per_feature_zscore",
        "n_zones": n_zones,
        "feature_keys": feature_keys,
        "feature_units": feature_units,
        "unscored_sample_ids": unscored_ids,
        "zones": zones,
        "features": [asdict(z) for z in zone_features],
    }


BASE_RATES = {
    "wheat": {
        "nitrogen": (140, "kgN/ha"),
        "seed": (160, "kg/ha"),
        "irrigation": (45, "mm"),
        "phosphorus": (60, "kgP2O5/ha"),
        "potassium": (50, "kgK2O/ha"),
    },
    "maize": {
        "nitrogen": (190, "kgN/ha"),
        "seed": (25, "kg/ha"),
        "irrigation": (55, "mm"),
        "phosphorus": (70, "kgP2O5/ha"),
        "potassium": (75, "kgK2O/ha"),
    },
    "potato": {
        "nitrogen": (180, "kgN/ha"),
        "seed": (2500, "kg/ha"),
        "irrigation": (35, "mm"),
        "phosphorus": (95, "kgP2O5/ha"),
        "potassium": (160, "kgK2O/ha"),
    },
    "default": {
        "nitrogen": (120, "kgN/ha"),
        "seed": (100, "kg/ha"),
        "irrigation": (40, "mm"),
        "phosphorus": (50, "kgP2O5/ha"),
        "potassium": (50, "kgK2O/ha"),
    },
}


def generate_prescription_map(
    zone_features: list[dict[str, Any]],
    *,
    crop: str,
    prescription_type: str,
    target_yield_t_ha: float | None = None,
) -> dict[str, Any]:
    crop_key = crop.lower()
    base_rate, unit = BASE_RATES.get(crop_key, BASE_RATES["default"]).get(
        prescription_type, BASE_RATES["default"].get(prescription_type, (100, "unit/ha"))
    )
    if target_yield_t_ha and prescription_type in {"nitrogen", "phosphorus", "potassium"}:
        base_rate *= max(0.7, min(1.4, target_yield_t_ha / 5.0))
    features: list[PrescriptionFeature] = []
    for z in zone_features:
        if prescription_type in {"nitrogen", "phosphorus", "potassium"}:
            # Preserve an explicit zero and reject invalid quantities at the recipe boundary.
            raw_multiplier = _zone_rate_multiplier(z)
            recipe_elemental_input(raw_multiplier, unit)
            mult = float(raw_multiplier)
        else:
            # G10: 0 صريح (منطقة استثناء) يبقى 0 — كان ``or 1.0`` يمنحها الجرعة كاملة.
            mult = _require_nonnegative(_zone_rate_multiplier(z), "rate_multiplier")
        zone = int(z.get("zone", 1))
        label = str(z.get("label", f"zone_{zone}"))
        # Stress zones receive more water/fertilizer but lower seed density.
        if prescription_type == "seed" and label in {"stress", "low"}:
            mult *= 0.92
        elif prescription_type in {"nitrogen", "irrigation"} and label in {"stress", "low"}:
            mult *= 1.08
        rate = round(base_rate * mult, 2)
        features.append(
            PrescriptionFeature(
                id=str(z.get("id") or _stable_id(z, "rx")),
                zone=zone,
                prescription_type=prescription_type,
                crop=crop,
                rate=rate,
                unit=unit,
                properties={
                    "source_label": label,
                    "rate_multiplier": round(mult, 3),
                    **(
                        {"recipe_input": recipe_elemental_input(rate, unit)}
                        if prescription_type in {"nitrogen", "phosphorus", "potassium"}
                        else {}
                    ),
                },
            )
        )
    return {
        "type": "FeatureCollection",
        "prescription_type": prescription_type,
        "crop": crop,
        "unit": unit,
        "features": [
            {"type": "Feature", "id": f.id, "geometry": None, "properties": asdict(f)}
            for f in features
        ],
        "exports": ["GeoJSON", "Shapefile", "ISOXML", "JohnDeereOperationsCenter", "Trimble"],
    }


def _linear_trend(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    xm = mean(xs)
    ym = mean(values)
    denom = sum((x - xm) ** 2 for x in xs) or 1.0
    return sum((x - xm) * (y - ym) for x, y in zip(xs, values, strict=False)) / denom


def compute_yield_stability(
    history: dict[str, list[float]] | list[dict[str, Any]],
) -> dict[str, Any]:
    skipped_missing_yield = 0
    if isinstance(history, list):
        grouped: dict[str, list[float]] = {}
        for row in history:
            # إنتاجيّة غائبة تُستبعَد وتُعَدّ — كانت تدخل صفراً فتُخفِض المتوسّط.
            value = _finite_or_none(row.get("yield"))
            if value is None:
                skipped_missing_yield += 1
                continue
            grouped.setdefault(str(row.get("zone", "field")), []).append(value)
    else:
        grouped = {str(k): [float(x) for x in v] for k, v in history.items()}
    classes: list[YieldStabilityClass] = []
    for zone, vals in grouped.items():
        vals = [v for v in vals if math.isfinite(v)]
        if not vals:
            continue
        m = mean(vals)
        cv = (pstdev(vals) / m) if m else 0.0
        trend = _linear_trend(vals)
        if m >= 5 and cv <= 0.18:
            label = "stable_high"
        elif cv > 0.30:
            label = "unstable"
        elif trend > 0.15:
            label = "improving"
        elif trend < -0.15:
            label = "declining"
        elif m < 3:
            label = "stable_low"
        else:
            label = "moderate_stable"
        classes.append(
            YieldStabilityClass(
                zone=zone,
                label=label,
                mean_yield=round(m, 3),
                cv=round(cv, 3),
                trend=round(trend, 3),
                years=len(vals),
            )
        )
    return {
        "classes": [asdict(c) for c in classes],
        "count": len(classes),
        "skipped_missing_yield": skipped_missing_yield,
    }


# الأساس الموحَّد للإنتاجيّة في هذه الوحدة: طن/هكتار. تحويل صريح فقط لما يُعرَف.
_YIELD_UNIT_TO_T_HA = {"t/ha": 1.0, "kg/ha": 0.001}


def _zone_yield_t_ha(z: dict[str, Any]) -> float | None:
    """إنتاجيّة المنطقة بـ t/ha أو None إن غابت — لا 3 ط/هـ مُختلَقة ولا ``score``.

    ``score`` درجةُ تقسيم بلا وحدة لا إنتاجيّة. ``mean_yield`` يتبع ``yield_unit``
    (غيابها ⇒ t/ha، أساس ``compute_yield_stability``). وحدة مجهولة أو متعارضة مع
    ``expected_yield_t_ha`` ⇒ ValueError صريح.
    """
    unit = z.get("yield_unit")
    if unit is not None and unit not in _YIELD_UNIT_TO_T_HA:
        raise ValueError(
            f"unsupported yield_unit {unit!r}; expected one of {sorted(_YIELD_UNIT_TO_T_HA)}"
        )
    if z.get("expected_yield_t_ha") is not None:
        if unit not in (None, "t/ha"):
            raise ValueError(f"expected_yield_t_ha is in t/ha but yield_unit={unit!r}")
        return _require_nonnegative(z["expected_yield_t_ha"], "expected_yield_t_ha")
    if z.get("mean_yield") is not None:
        value = _require_nonnegative(z["mean_yield"], "mean_yield")
        return value * _YIELD_UNIT_TO_T_HA[unit or "t/ha"]
    return None


def compute_profitability_map(
    zones: list[dict[str, Any]],
    *,
    market_price_per_t: float,
    variable_costs_per_ha: dict[str, float] | None = None,
) -> dict[str, Any]:
    variable_costs_per_ha = variable_costs_per_ha or {}
    base_cost = sum(_safe_float(v) for v in variable_costs_per_ha.values())
    features: list[ProfitabilityFeature] = []
    missing_yield: list[str] = []
    for z in zones:
        zone_no = int(z.get("zone", 1))
        feature_id = str(z.get("id") or _stable_id(z, "profit"))
        expected_yield = _zone_yield_t_ha(z)
        raw_adjustment = z.get("cost_adjustment")
        if raw_adjustment is None:
            raw_adjustment = _zone_rate_multiplier(z)
        cost_adjustment = _require_nonnegative(raw_adjustment, "cost_adjustment")
        total_cost = round(base_cost * max(0.2, cost_adjustment), 2)
        if expected_yield is None:
            # بلا إنتاجيّة لا إيراد ولا ربح يُحسَب — المنطقة تُعلَن ناقصة البيانات.
            missing_yield.append(feature_id)
            revenue = profit = roi = None
            label = "insufficient_data"
            status = "missing_yield"
        else:
            revenue = round(expected_yield * market_price_per_t, 2)
            profit = round(revenue - total_cost, 2)
            roi = round(profit / total_cost, 3) if total_cost else 0.0
            label = (
                "high_profit"
                if profit > total_cost * 0.5
                else "medium_profit"
                if profit >= 0
                else "loss_area"
            )
            status = "ok"
        features.append(
            ProfitabilityFeature(
                id=feature_id,
                zone=zone_no,
                gross_revenue_per_ha=revenue,
                total_cost_per_ha=total_cost,
                profit_per_ha=profit,
                roi=roi,
                label=label,
                data_status=status,
            )
        )
    return {
        "features": [asdict(f) for f in features],
        "currency": "configured_market_currency",
        "basis": "per_ha",
        "yield_unit": "t/ha",
        "zones_missing_yield": missing_yield,
    }


def compose_digital_twin_snapshot(
    *,
    farm: dict[str, Any],
    fields: list[dict[str, Any]] | None = None,
    weather: dict[str, Any] | None = None,
    soil: dict[str, Any] | None = None,
    irrigation: dict[str, Any] | None = None,
    equipment: list[dict[str, Any]] | None = None,
    economics: dict[str, Any] | None = None,
    ai: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fields = fields or []
    equipment = equipment or []
    # Client-submitted farm snapshots are display-only. An empty/unknown field
    # state is not an observed 100/100 healthy farm.
    known_field_statuses = {
        "ok", "healthy", "normal", "stress", "critical",
        "warning", "blocked", "needs_attention",
    }
    fully_classified = bool(fields) and all(
        isinstance(f, dict) and str(f.get("status", "")).lower() in known_field_statuses
        for f in fields
    )
    stress_fields = [
        f for f in fields
        if str(f.get("status", "")).lower()
        in {"stress", "critical", "warning", "blocked", "needs_attention"}
    ]
    offline_equipment = [
        e
        for e in equipment
        if str(e.get("status", "")).lower() in {"offline", "fault", "maintenance"}
    ]
    health_score = 100
    health_score -= min(35, len(stress_fields) * 8)
    health_score -= min(20, len(offline_equipment) * 5)
    if irrigation and str(irrigation.get("status", "")).lower() in {"deficit", "over_irrigation"}:
        health_score -= 10
    if weather and str(weather.get("risk", "")).lower() in {"high", "critical"}:
        health_score -= 10
    snapshot = {
        # Fingerprint every supplied fact. Same farm and same day but different
        # field or equipment states MUST NOT share an identifier.
        "snapshot_id": _stable_id(
            {
                "farm": farm, "fields": fields, "weather": weather,
                "soil": soil, "irrigation": irrigation, "equipment": equipment,
                "economics": economics, "ai": ai,
            },
            "twin",
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "farm": farm,
        "field_count": len(fields),
        "equipment_count": len(equipment),
        "state": {
            "fields": fields,
            "weather": weather or {},
            "soil": soil or {},
            "irrigation": irrigation or {},
            "equipment": equipment,
            "economics": economics or {},
            "ai": ai or {},
        },
        "health_score": max(0, min(100, health_score)) if fully_classified else None,
        "health_score_status": "estimated_from_client_status"
        if fully_classified
        else "not_evaluated_missing_field_status",
        "source_authority": "client_supplied_preview",
        "preview_only": True,
        "decision_eligible": False,
        "alerts": [
            *[
                {"type": "field_stress", "field_id": f.get("field_id") or f.get("id")}
                for f in stress_fields
            ],
            *[
                {
                    "type": "equipment_attention",
                    "equipment_id": e.get("equipment_id") or e.get("id"),
                }
                for e in offline_equipment
            ],
        ],
    }
    return snapshot
