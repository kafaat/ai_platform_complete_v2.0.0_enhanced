"""core/drift_geometry.py — خطر انجراف الرشّ نحو المناطق الحسّاسة (downwind) — منطق صرف.

يبني على محرّك الرياح (``wind_geometry``): إذا كان الرشّ يتّجه مع الريح، فأيّ منطقة حسّاسة
(منزل/طريق/قناة ماء/حقل مجاور/منحل/ماشية) تقع في **مخروط downwind** أمام الحقل تكون معرّضة
لانجراف المبيد. يجيب: هل الرشّ آمن الآن من ناحية الجوار؟ ومن أيّ اتّجاه يأتي الخطر؟

**صدق حاسم:**
  • بلا اتّجاه ريح ⇒ ``unknown`` (لا حكم انجراف بلا ريح).
  • **تقريب معلَن (الشريحة 1):** الأصل مركز الحقل (لا حافّته الحقيقيّة downwind)، والعازل
    مخروط بنصف-زاوية ثابت — تقدير محافظ لا هندسة مضلّع دقيقة (تأتي في شريحة GIS لاحقة).
  • اتّجاه الريح **أرصاديّ** (يأتي منه)؛ الانجراف يتّجه إلى (اتّجاه+180).

هندسة كرويّة نقيّة (haversine + bearing) — بلا shapely/I/O؛ تُختبَر بأرقام عاديّة.
"""

from __future__ import annotations

import math
from typing import Any

_EARTH_R_M = 6_371_000.0  # نصف قطر الأرض (متر) — haversine.
_DEFAULT_HALF_ANGLE_DEG = 30.0  # نصف زاوية مخروط الانجراف (محافظ: ±30° حول اتّجاه الريح).


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """المسافة الكرويّة بالأمتار بين نقطتين (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_R_M * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """السَّمت الأوّليّ (0..360، شمال=0) من النقطة 1 إلى النقطة 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360.0


def _angular_diff(a: float, b: float) -> float:
    """أصغر فرق زاويّ (0..180) بين سَمتين."""
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def downwind_azimuth(wind_from_deg: Any) -> float | None:
    """اتّجاه **تحرّك** الانجراف = (اتّجاه الريح الأرصاديّ + 180). غير رقميّ ⇒ None."""
    d = _num(wind_from_deg)
    return None if d is None else (d + 180.0) % 360.0


def zone_drift_exposure(
    field_lat: Any,
    field_lon: Any,
    wind_from_deg: Any,
    target_lat: Any,
    target_lon: Any,
    *,
    max_distance_m: float = 200.0,
    half_angle_deg: float = _DEFAULT_HALF_ANGLE_DEG,
) -> dict[str, Any]:
    """هل تقع نقطة حسّاسة في مخروط الانجراف downwind للحقل؟ (تقدير محافظ).

    ``exposed=True`` إذا كانت ضمن ``max_distance_m`` **و** سَمتها من الحقل قريب من اتّجاه
    الانجراف (فرق ≤ ``half_angle_deg``). بلا ريح/إحداثيّات ⇒ ``exposed=None`` + سبب (لا حكم).
    """
    fl, fo = _num(field_lat), _num(field_lon)
    tl, to = _num(target_lat), _num(target_lon)
    drift_to = downwind_azimuth(wind_from_deg)
    if drift_to is None:
        return {"exposed": None, "reason": "no_wind"}
    if None in (fl, fo, tl, to):
        return {"exposed": None, "reason": "no_coordinates"}
    dist = haversine_m(fl, fo, tl, to)
    brg = bearing_deg(fl, fo, tl, to)
    angle_off = _angular_diff(brg, drift_to)
    exposed = dist <= float(max_distance_m) and angle_off <= float(half_angle_deg)
    return {
        "exposed": exposed,
        "distance_m": round(dist, 1),
        "bearing_deg": round(brg, 1),
        "drift_azimuth_deg": round(drift_to, 1),
        "angle_off_deg": round(angle_off, 1),
        "reason": None,
    }


def spray_drift_risk(
    field_lat: Any,
    field_lon: Any,
    wind_from_deg: Any,
    sensitive_zones: Any,
    *,
    max_distance_m: float = 200.0,
    half_angle_deg: float = _DEFAULT_HALF_ANGLE_DEG,
) -> dict[str, Any]:
    """يقيّم خطر انجراف الرشّ نحو قائمة مناطق حسّاسة (صدق: بلا ريح ⇒ unknown).

    ``sensitive_zones``: عناصرها ``{id?, type?, lat, lon}``. يُرجِع المناطق المعرّضة + ملخّصاً.
    القرار النهائيّ ميدانيّ؛ هذا تقدير محافظ (مخروط من مركز الحقل) لتنبيه «لا ترشّ الآن نحو X».
    """
    drift_to = downwind_azimuth(wind_from_deg)
    if drift_to is None:
        return {"status": "unknown", "reason": "no_wind", "exposed_zones": [], "n_zones": 0}
    if not isinstance(sensitive_zones, (list, tuple)):
        sensitive_zones = []
    exposed: list[dict[str, Any]] = []
    evaluated = 0
    for z in sensitive_zones:
        if not isinstance(z, dict):
            continue
        exp = zone_drift_exposure(
            field_lat,
            field_lon,
            wind_from_deg,
            z.get("lat"),
            z.get("lon"),
            max_distance_m=max_distance_m,
            half_angle_deg=half_angle_deg,
        )
        if exp.get("exposed") is None:
            continue
        evaluated += 1
        if exp["exposed"]:
            exposed.append(
                {
                    "id": z.get("id"),
                    "type": z.get("type"),
                    "distance_m": exp["distance_m"],
                    "bearing_deg": exp["bearing_deg"],
                }
            )
    exposed.sort(key=lambda e: e["distance_m"])
    return {
        "status": "at_risk" if exposed else "clear",
        "reason": None,
        "drift_azimuth_deg": round(drift_to, 1),
        "max_distance_m": float(max_distance_m),
        "half_angle_deg": float(half_angle_deg),
        "n_zones": evaluated,
        "exposed_zones": exposed,
        "note_ar": (
            "تقدير محافظ (مخروط من مركز الحقل) — لا ترشّ نحو المناطق المعرّضة الآن؛ "
            "القرار النهائيّ ميدانيّ."
        ),
    }
