"""Productivity zones + daily AI agronomist primitives for SAHOOL.

The functions here are deliberately pure and conservative. They turn already-known
field signals into management-zone summaries and daily action briefs without
inventing satellite, lab, weather, machinery or yield data. They are intended to
support a OneSoil-like workflow:

Satellite/history -> productivity zones -> sampling plan -> lab results ->
prescription maps -> tasks -> field diary -> AI daily brief.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Literal

ZoneClass = Literal["low", "medium", "high", "problem"]
ActionPriority = Literal["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class ProductivityObservation:
    """One observation/cell/zone candidate from remote sensing or yield history.

    lat/lng are optional: when present they allow the frontend/API to render points
    or derive sample targets. Missing coordinates are kept out of generated sample
    points instead of being fabricated.
    """

    id: str
    area_ha: float
    ndvi_mean: float | None = None
    ndvi_cv: float | None = None
    yield_rel: float | None = None  # relative to field average, e.g. 0.85/1.15
    soil_ec_dsm: float | None = None
    soil_ph: float | None = None
    lat: float | None = None
    lng: float | None = None


@dataclass(frozen=True)
class ProductivityZone:
    zone_id: str
    zone_class: ZoneClass
    area_ha: float
    observation_ids: list[str]
    score: float
    confidence: float
    limiting_factors_ar: list[str] = field(default_factory=list)
    sampling_priority: ActionPriority = "medium"


@dataclass(frozen=True)
class DailyAction:
    action_id: str
    priority: ActionPriority
    title_ar: str
    reason_ar: str
    field_id: str | None = None
    zone_id: str | None = None
    source: str = "derived"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _norm_ndvi(ndvi: float | None) -> float | None:
    if ndvi is None:
        return None
    # Most crop NDVI useful range; values outside are clipped, not trusted blindly.
    return _clamp((ndvi - 0.20) / 0.65, 0.0, 1.0)


def productivity_score(obs: ProductivityObservation) -> tuple[float | None, list[str], float]:
    """Return (score 0..1 or None, limiting factors, confidence).

    Confidence increases with multiple independent sources and decreases when the
    zone has high within-zone NDVI variability.
    """
    factors: list[float] = []
    confidence_parts: list[float] = []
    limits: list[str] = []

    ndvi = _norm_ndvi(obs.ndvi_mean)
    if ndvi is not None:
        factors.append(ndvi)
        confidence_parts.append(0.35)
        if ndvi < 0.35:
            limits.append("غطاء نباتي منخفض تاريخياً")

    if obs.yield_rel is not None:
        # 0.6x average -> 0, 1.4x average -> 1.
        y = _clamp((obs.yield_rel - 0.60) / 0.80, 0.0, 1.0)
        factors.append(y)
        confidence_parts.append(0.35)
        if obs.yield_rel < 0.85:
            limits.append("إنتاجية تاريخية دون متوسط الحقل")

    if obs.soil_ec_dsm is not None:
        # Salinity is a penalty: <=2 no penalty, >=8 severe.
        salinity_health = 1.0 - _clamp((obs.soil_ec_dsm - 2.0) / 6.0, 0.0, 1.0)
        factors.append(salinity_health)
        confidence_parts.append(0.20)
        if obs.soil_ec_dsm >= 4.0:
            limits.append("ملوحة تربة مؤثرة")

    if obs.soil_ph is not None:
        ph_health = (
            1.0 if 6.0 <= obs.soil_ph <= 7.8 else 0.65 if 5.5 <= obs.soil_ph <= 8.5 else 0.35
        )
        factors.append(ph_health)
        confidence_parts.append(0.10)
        if obs.soil_ph < 5.5 or obs.soil_ph > 8.5:
            limits.append("pH خارج النطاق الملائم")

    if not factors:
        return None, ["لا توجد إشارات كافية لتصنيف الإنتاجية"], 0.0

    score = mean(factors)
    confidence = min(0.95, sum(confidence_parts))
    if obs.ndvi_cv is not None and obs.ndvi_cv > 0.25:
        confidence *= 0.75
        limits.append("تذبذب NDVI عالٍ داخل المنطقة")
    return round(score, 3), limits, round(confidence, 3)


def classify_productivity_zone(obs: ProductivityObservation) -> ProductivityZone:
    score, limits, confidence = productivity_score(obs)
    if score is None:
        zclass: ZoneClass = "problem"
    elif obs.soil_ec_dsm is not None and obs.soil_ec_dsm >= 8.0:
        zclass = "problem"
        limits = [*limits, "ملوحة شديدة تحتاج خطة علاج قبل رفع المدخلات"]
    elif score < 0.40:
        zclass = "low"
    elif score < 0.68:
        zclass = "medium"
    else:
        zclass = "high"

    priority: ActionPriority = (
        "high" if zclass in {"low", "problem"} else "medium" if zclass == "medium" else "low"
    )
    return ProductivityZone(
        zone_id=f"zone-{obs.id}",
        zone_class=zclass,
        area_ha=max(0.0, obs.area_ha),
        observation_ids=[obs.id],
        score=score if score is not None else 0.0,
        confidence=confidence,
        limiting_factors_ar=limits,
        sampling_priority=priority,
    )


def build_productivity_zones(observations: list[ProductivityObservation]) -> dict:
    """Build a transparent management-zone summary from supplied observations."""
    zones = [classify_productivity_zone(o) for o in observations if o.area_ha > 0]
    total_area = sum(z.area_ha for z in zones)
    by_class: dict[str, dict] = {}
    for z in zones:
        row = by_class.setdefault(
            z.zone_class, {"area_ha": 0.0, "count": 0, "scores": [], "limiting_factors_ar": []}
        )
        row["area_ha"] += z.area_ha
        row["count"] += 1
        row["scores"].append(z.score)
        row["limiting_factors_ar"].extend(z.limiting_factors_ar)
    for row in by_class.values():
        row["area_ha"] = round(row["area_ha"], 3)
        row["area_pct"] = round((row["area_ha"] / total_area) * 100, 1) if total_area > 0 else 0.0
        row["mean_score"] = round(mean(row.pop("scores")), 3) if row.get("scores") else 0.0
        row["limiting_factors_ar"] = sorted(set(row["limiting_factors_ar"]))
    confidence_values = [z.confidence for z in zones]
    return {
        "zones": [z.__dict__ for z in zones],
        "summary": by_class,
        "total_area_ha": round(total_area, 3),
        "mean_confidence": round(mean(confidence_values), 3) if confidence_values else 0.0,
        "data_sufficiency": "sufficient"
        if len(zones) >= 3 and max(confidence_values or [0]) >= 0.35
        else "limited",
    }


def generate_zone_sampling_plan(
    observations: list[ProductivityObservation],
    *,
    samples_per_low_zone: int = 3,
    samples_per_medium_zone: int = 2,
    samples_per_high_zone: int = 1,
) -> dict:
    """Create a zone-based sampling plan from observations with coordinates.

    Coordinates are used only when provided. Observations without coordinates are
    reported as unplaceable instead of generating fake GPS sample points.
    """
    points: list[dict] = []
    unplaceable: list[str] = []
    for obs in observations:
        zone = classify_productivity_zone(obs)
        if obs.lat is None or obs.lng is None:
            unplaceable.append(obs.id)
            continue
        if zone.zone_class in {"problem", "low"}:
            n = samples_per_low_zone
        elif zone.zone_class == "medium":
            n = samples_per_medium_zone
        else:
            n = samples_per_high_zone
        for i in range(n):
            # tiny deterministic offset avoids stacking repeated planned cores while
            # staying near the provided observation point. Not a replacement for a
            # real field-walk route planner.
            delta = (i - (n - 1) / 2) * 0.00008
            points.append(
                {
                    "sample_id": f"{obs.id}-S{i + 1}",
                    "zone_id": zone.zone_id,
                    "zone_class": zone.zone_class,
                    "latitude": round(obs.lat + delta, 7),
                    "longitude": round(obs.lng + delta, 7),
                    "depth_cm_from": 0,
                    "depth_cm_to": 30,
                    "priority": zone.sampling_priority,
                    "reason_ar": "; ".join(zone.limiting_factors_ar)
                    or "خطة عيّنة حسب منطقة إنتاجية",
                }
            )
    return {
        "sample_points": points,
        "unplaceable_observation_ids": unplaceable,
        "count": len(points),
    }


def _first_number(signals: dict, *keys: str) -> float | None:
    """Return the first finite numeric value for a set of common signal aliases."""
    for key in keys:
        value = signals.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _first_value(signals: dict, *keys: str):
    for key in keys:
        if key in signals and signals.get(key) is not None:
            return signals.get(key)
    return None


def build_daily_ai_brief(
    *, field_id: str | None, signals: dict, tasks: list[dict] | None = None
) -> dict:
    """Compress field signals into a daily actionable brief.

    The function is intentionally rule-based and source-labelled. It does not call
    an LLM; the AI advisor can later use this as grounded context. It accepts
    multiple common aliases used by satellite/weather/lab services so the brief is
    useful even when upstream payloads are named slightly differently.
    """
    actions: list[DailyAction] = []
    tasks = tasks or []

    ndvi_drop = _first_number(
        signals, "ndvi_drop_pct", "ndvi_delta_pct", "vegetation_drop_pct", "ndvi_anomaly_pct"
    )
    if isinstance(ndvi_drop, (int, float)) and ndvi_drop >= 10:
        actions.append(
            DailyAction(
                action_id="inspect-ndvi-drop",
                priority="high",
                field_id=field_id,
                title_ar="افحص انخفاض الغطاء النباتي اليوم",
                reason_ar=f"انخفض NDVI بنحو {ndvi_drop:.0f}%؛ راجع الري والآفات ونقاط الاستكشاف.",
                source="satellite",
            )
        )

    vpd = _first_number(signals, "vpd_kpa", "vpd")
    et0 = _first_number(signals, "et0_mm_day", "et0", "et0_mm", "reference_et_mm_day")
    if isinstance(vpd, (int, float)) and vpd >= 2.5:
        actions.append(
            DailyAction(
                action_id="water-stress-watch",
                priority="high" if isinstance(et0, (int, float)) and et0 >= 6 else "medium",
                field_id=field_id,
                title_ar="راجع نافذة الري بسبب طلب تبخري مرتفع",
                reason_ar=f"VPD={vpd:.1f} kPa{f' و ET0={et0:.1f} مم/يوم' if isinstance(et0, (int, float)) else ''}.",
                source="weather",
            )
        )

    wind = _first_number(signals, "wind_speed_kmh", "wind_kmh", "wind_speed", "wind_speed_10m_kmh")
    if isinstance(wind, (int, float)) and wind > 18:
        actions.append(
            DailyAction(
                action_id="spray-window-blocked",
                priority="medium",
                field_id=field_id,
                title_ar="أجّل الرش حتى تهدأ الرياح",
                reason_ar=f"سرعة الرياح {wind:.0f} كم/س أعلى من نافذة الرش الآمنة.",
                source="weather",
            )
        )

    lab_gate = _first_value(signals, "lab_recommendation_gate", "soil_lab_gate", "water_lab_gate")
    if lab_gate == "needs_review":
        actions.append(
            DailyAction(
                action_id="lab-review-needed",
                priority="medium",
                field_id=field_id,
                title_ar="راجع نتائج المختبر قبل اعتماد التسميد",
                reason_ar="نتائج التربة/المياه غير مكتملة أو غير معتمدة؛ لا تُحوّلها إلى وصفة نهائية.",
                source="lab",
            )
        )

    soil_ec = _first_number(signals, "soil_ec_dsm", "soil_ec", "ec_dsm")
    if soil_ec is not None and soil_ec >= 4:
        actions.append(
            DailyAction(
                action_id="salinity-zone-review",
                priority="high" if soil_ec >= 8 else "medium",
                field_id=field_id,
                title_ar="راجع مناطق الملوحة قبل زيادة المدخلات",
                reason_ar=f"EC التربة {soil_ec:.1f} dS/m؛ اربط التسميد والري بمناطق الإنتاجية وخطة الغسيل.",
                source="soil_lab",
            )
        )

    water_ec = _first_number(signals, "water_ec_dsm", "irrigation_water_ec", "water_ec")
    sar = _first_number(signals, "water_sar", "sar")
    if water_ec is not None and water_ec >= 2.5:
        actions.append(
            DailyAction(
                action_id="water-quality-watch",
                priority="high" if water_ec >= 4 or (sar is not None and sar >= 9) else "medium",
                field_id=field_id,
                title_ar="راجع جودة مياه الري قبل الجدولة",
                reason_ar=f"EC مياه الري {water_ec:.1f} dS/m{f' و SAR={sar:.1f}' if sar is not None else ''}. عدّل الري والغسيل حسب حساسية المحصول.",
                source="water_lab",
            )
        )

    overdue = [
        t for t in tasks if str(t.get("status")) in {"pending", "in_progress"} and t.get("overdue")
    ]
    if overdue:
        actions.append(
            DailyAction(
                action_id="overdue-tasks",
                priority="high",
                field_id=field_id,
                title_ar="أغلق المهام اليومية المتأخرة",
                reason_ar=f"يوجد {len(overdue)} مهمة متأخرة تحتاج متابعة أو إعادة جدولة.",
                source="workflow",
            )
        )

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    # De-duplicate repeated rules by action_id while preserving the highest priority.
    deduped: dict[str, DailyAction] = {}
    for action in actions:
        current = deduped.get(action.action_id)
        if current is None or priority_order[action.priority] < priority_order[current.priority]:
            deduped[action.action_id] = action
    actions = sorted(deduped.values(), key=lambda a: priority_order[a.priority])
    if not actions:
        actions.append(
            DailyAction(
                action_id="no-critical-action",
                priority="low",
                field_id=field_id,
                title_ar="لا يوجد إجراء عاجل من الإشارات المتاحة",
                reason_ar="الإشارات الحالية لا تكفي لإطلاق تنبيه تشغيلي؛ استمر في المراقبة.",
                source="derived",
            )
        )
    return {
        "field_id": field_id,
        "headline_ar": actions[0].title_ar,
        "actions": [a.__dict__ for a in actions],
        "source_count": len([k for k, v in signals.items() if v is not None]),
        "is_grounded": bool(signals or tasks),
        "decision_policy": "grounded_actions_only_no_fabricated_remote_sensing",
    }
