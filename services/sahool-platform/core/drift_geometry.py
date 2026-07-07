"""core/drift_geometry.py — خطر انجراف الرشّ نحو المناطق الحسّاسة (downwind) — منطق صرف.

يبني على محرّك الرياح (``wind_geometry``): إذا كان الرشّ يتّجه مع الريح، فأيّ منطقة حسّاسة
(منزل/طريق/قناة ماء/حقل مجاور/منحل/ماشية) تقع في **مخروط downwind** أمام الحقل تكون معرّضة
لانجراف المبيد. يجيب: هل الرشّ آمن الآن من ناحية الجوار؟ ومن أيّ اتّجاه يأتي الخطر؟

**صدق حاسم:**
  • بلا اتّجاه ريح ⇒ ``unknown`` (لا حكم انجراف بلا ريح).
  • **الأصل (الشريحة 2 — حافّة المضلّع):** عند تمرير ``field_polygon`` يصير أصل الانجراف
    **رأس الحدّ الأكثر تجاه downwind** (أقرب حافّة للجوار المُعرَّض)، لا مركز الحقل —
    تقدير أدقّ. بلا مضلّع ⇒ يبقى مركز الحقل (سلوك الشريحة 1، متوافق للخلف).
    يبقى العازل مخروطاً بنصف-زاوية ثابت (تقريب محافظ معلَن، لا قناع رشّ دقيق).
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


def exterior_ring_from_geojson(geom: Any) -> Any:
    """يستخرج الحلقة الخارجيّة (إحداثيّات ``[lon, lat]``) من GeoJSON Polygon/MultiPolygon.

    غير معروف/شاذّ ⇒ None (لا اختلاق). يُمرَّر الناتج لـ``downwind_edge_point``.
    """
    if not isinstance(geom, dict):
        return None
    gtype, coords = geom.get("type"), geom.get("coordinates")
    if gtype == "Polygon" and isinstance(coords, list) and coords:
        return coords[0]
    if (
        gtype == "MultiPolygon"
        and isinstance(coords, list)
        and coords
        and isinstance(coords[0], list)
        and coords[0]
    ):
        return coords[0][0]  # الحلقة الخارجيّة لأوّل مضلّع
    return None


def _clean_ring(polygon: Any) -> list[tuple[float, float]]:
    """يُطبِّع مُدخل مضلّع (GeoJSON dict أو حلقة ``[lon, lat]``) إلى ``[(lat, lon), …]``.

    يُسقط النقاط الشاذّة ويحذف رأس الإغلاق المكرّر. فارغ/شاذّ ⇒ قائمة فارغة.
    """
    coords = polygon if isinstance(polygon, (list, tuple)) else exterior_ring_from_geojson(polygon)
    if not isinstance(coords, (list, tuple)):
        return []
    ring: list[tuple[float, float]] = []
    for c in coords:
        if not isinstance(c, (list, tuple)) or len(c) < 2:
            continue
        lon, lat = _num(c[0]), _num(c[1])
        if lon is None or lat is None:
            continue
        ring.append((lat, lon))
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]  # حلقة مُغلَقة — لا نُكرّر الرأس.
    return ring


def polygon_representative_point(polygon: Any) -> tuple[float, float] | None:
    """نقطة مرجعيّة داخليّة تقريبيّة = **متوسّط الرؤوس** (لا مركز مساحة دقيق — معلَن).

    تكفي كمرجع لاختيار الرأس الأكثر تجاه downwind. حلقة فارغة ⇒ None.
    """
    ring = _clean_ring(polygon)
    if not ring:
        return None
    return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))


def downwind_edge_point(
    polygon: Any,
    wind_from_deg: Any,
    *,
    center: tuple[float, float] | None = None,
) -> tuple[float, float] | None:
    """رأس الحدّ **الأكثر تجاه downwind** — أصل انجراف أدقّ من مركز الحقل.

    يُسقِط كلّ رأس على محور الانجراف (من النقطة المرجعيّة) ويختار الأبعد أماماً
    (``d·cos(bearing − drift)``). بلا ريح/حلقة/مرجع ⇒ None (لا اختلاق).
    """
    drift_to = downwind_azimuth(wind_from_deg)
    if drift_to is None:
        return None
    ring = _clean_ring(polygon)
    if not ring:
        return None
    ref = center if center is not None else polygon_representative_point(polygon)
    if ref is None:
        return None
    clat, clon = ref
    best: tuple[float, float] | None = None
    best_proj: float | None = None
    for lat, lon in ring:
        d = haversine_m(clat, clon, lat, lon)
        b = bearing_deg(clat, clon, lat, lon)
        proj = d * math.cos(math.radians(b - drift_to))  # مركّبة على محور الانجراف
        if best_proj is None or proj > best_proj:
            best_proj, best = proj, (lat, lon)
    return best


def _polygon_zone_exposure(
    center: tuple[float, float],
    ring: list[tuple[float, float]],
    drift_to: float,
    target_lat: Any,
    target_lon: Any,
    max_distance_m: float,
    half_angle_deg: float,
) -> dict[str, Any]:
    """تعرّض منطقة في وضع المضلّع: الزاوية من **مركز الحقل** (هل هي downwind للحقل؟)،
    والمسافة من **أقرب رأس حدّ** (قرب فعليّ من الحافّة لا من المركز). إحداثيّات شاذّة ⇒ None.
    """
    tl, to = _num(target_lat), _num(target_lon)
    if None in (tl, to):
        return {"exposed": None, "reason": "no_coordinates"}
    clat, clon = center
    brg = bearing_deg(clat, clon, tl, to)
    angle_off = _angular_diff(brg, drift_to)
    dist = min(haversine_m(vlat, vlon, tl, to) for vlat, vlon in ring)
    exposed = dist <= float(max_distance_m) and angle_off <= float(half_angle_deg)
    return {
        "exposed": exposed,
        "distance_m": round(dist, 1),
        "bearing_deg": round(brg, 1),
        "angle_off_deg": round(angle_off, 1),
        "reason": None,
    }


def spray_drift_risk(
    field_lat: Any,
    field_lon: Any,
    wind_from_deg: Any,
    sensitive_zones: Any,
    *,
    field_polygon: Any = None,
    max_distance_m: float = 200.0,
    half_angle_deg: float = _DEFAULT_HALF_ANGLE_DEG,
) -> dict[str, Any]:
    """يقيّم خطر انجراف الرشّ نحو قائمة مناطق حسّاسة (صدق: بلا ريح ⇒ unknown).

    ``sensitive_zones``: عناصرها ``{id?, type?, lat, lon}``. ``field_polygon`` اختياريّ
    (GeoJSON Polygon/MultiPolygon أو حلقة ``[lon, lat]``): عند توفّره تُقاس **المسافة من
    أقرب حدّ للحقل** (لا من مركزه) بينما تبقى **الزاوية من المركز** (هل المنطقة downwind
    للحقل؟) — أدقّ وأكثر أماناً (مسافة أقصر ⇒ تنبيه أبكر). ``origin_mode`` =
    polygon_boundary/center، و``drift_origin`` = رأس الحدّ الأكثر تجاه downwind (للعرض).
    """
    drift_to = downwind_azimuth(wind_from_deg)
    if drift_to is None:
        return {"status": "unknown", "reason": "no_wind", "exposed_zones": [], "n_zones": 0}
    ring = _clean_ring(field_polygon) if field_polygon is not None else []
    use_poly = bool(ring)
    center: tuple[float, float] | None
    if use_poly:
        center = polygon_representative_point(field_polygon)
        origin_mode = "polygon_boundary"
    else:
        fl, fo = _num(field_lat), _num(field_lon)
        center = (fl, fo) if None not in (fl, fo) else None
        origin_mode = "center"

    if not isinstance(sensitive_zones, (list, tuple)):
        sensitive_zones = []
    exposed: list[dict[str, Any]] = []
    evaluated = 0
    for z in sensitive_zones:
        if not isinstance(z, dict):
            continue
        if use_poly and center is not None:
            exp = _polygon_zone_exposure(
                center, ring, drift_to, z.get("lat"), z.get("lon"), max_distance_m, half_angle_deg
            )
        else:
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
    drift_origin = downwind_edge_point(field_polygon, wind_from_deg) if use_poly else None
    origin_ar = "أقرب حدّ للحقل" if use_poly else "مركز الحقل"
    return {
        "status": "at_risk" if exposed else "clear",
        "reason": None,
        "drift_azimuth_deg": round(drift_to, 1),
        "origin_mode": origin_mode,
        "drift_origin": (
            {"lat": round(drift_origin[0], 6), "lon": round(drift_origin[1], 6)}
            if drift_origin
            else None
        ),
        "max_distance_m": float(max_distance_m),
        "half_angle_deg": float(half_angle_deg),
        "n_zones": evaluated,
        "exposed_zones": exposed,
        "note_ar": (
            f"تقدير محافظ (زاوية من مركز الحقل، مسافة من {origin_ar}) — لا ترشّ نحو "
            "المناطق المعرّضة الآن؛ القرار النهائيّ ميدانيّ."
        ),
    }
