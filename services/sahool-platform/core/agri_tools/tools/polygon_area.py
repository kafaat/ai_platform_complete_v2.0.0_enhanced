"""أداة: حاسبة مساحة مضلّع حقل من إحداثيّات جغرافيّة (lon/lat) — نقيّة حتميّة.

تحسب مساحة المضلّع على سطح كرويّ (خوارزميّة المساحة الكرويّة المعياريّة — Chamberlain &
Duquette، المستخدَمة في Google Maps وLeaflet) بدلاً من صيغة المحدّد المستوية على الدرجات
(الخاطئة جغرافيّاً). تُرجِع المساحة (م² وهكتار)، والمحيط (هافرساين بالأمتار)، وعدد الرؤوس.
"""

from __future__ import annotations

import math

from ..registry import Tool, ToolParam, register

_R = 6378137.0  # نصف قطر الأرض WGS84 (متر)
_M2_PER_HA = 10_000.0


def _distinct_ring(coords: list) -> list:
    """يُرجِع حلقة الرؤوس بلا تكرار النقطة الأولى في النهاية (إن وُجد)."""
    if not isinstance(coords, (list, tuple)):
        raise ValueError("coordinates: expected a ring of longitude/latitude pairs")
    ring = []
    for point in coords:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("coordinates: expected a longitude/latitude pair")
        if any(isinstance(value, bool) for value in point):
            raise ValueError("coordinates: boolean coordinates are not valid")
        try:
            lon, lat = map(float, point)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("coordinates: invalid numeric coordinate") from exc
        if not (
            math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90
        ):
            raise ValueError("coordinates: longitude/latitude outside valid bounds")
        ring.append((lon, lat))
    if len(ring) >= 2 and ring[0] == ring[-1]:
        ring = ring[:-1]
    return ring


def _haversine_m(p1: tuple, p2: tuple) -> float:
    """مسافة هافرساين بين نقطتين (lon, lat) بالأمتار."""
    lon1, lat1 = p1
    lon2, lat2 = p2
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * _R * math.asin(math.sqrt(a))


def compute(inp: dict) -> dict:
    # يقبل قاموس المُدخَلات من السجلّ {"coordinates": [...]} أو قائمة الإحداثيّات مباشرةً.
    coords = inp["coordinates"] if isinstance(inp, dict) else inp
    ring = _distinct_ring(coords)
    if len(set(ring)) < 3:
        raise ValueError("مضلّع يحتاج 3 رؤوس على الأقلّ")

    # المساحة الكرويّة (Chamberlain & Duquette).
    area = 0.0
    n = len(ring)
    for i in range(n):
        lon1, lat1 = ring[i]
        lon2, lat2 = ring[(i + 1) % n]
        # Agricultural fields use the local, shortest longitude step, including at ±180°.
        delta_lon = lon2 - lon1
        if delta_lon > 180:
            delta_lon -= 360
        elif delta_lon < -180:
            delta_lon += 360
        area += math.radians(delta_lon) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    area = abs(area * _R * _R / 2.0)

    # المحيط (هافرساين على الحلقة المغلقة).
    perimeter = 0.0
    for i in range(n):
        perimeter += _haversine_m(ring[i], ring[(i + 1) % n])

    return {
        "area_m2": round(area, 2),
        "area_ha": round(area / _M2_PER_HA, 4),
        "perimeter_m": round(perimeter, 2),
        "vertex_count": n,
    }


register(
    Tool(
        id="polygon_area",
        name_ar="حاسبة مساحة مضلّع الحقل",
        category="geo",
        description_ar="مساحة ومحيط مضلّع حقل من إحداثيّات جغرافيّة (lon/lat) بحساب كرويّ دقيق.",
        params=[
            ToolParam(
                "coordinates",
                "geojson",
                "إحداثيّات حلقة المضلّع (lon/lat)",
            ),
        ],
        compute=compute,
        result_unit_ar="م² / هكتار / م",
        tags=("جغرافيا", "مساحة", "مضلّع", "حقل"),
    )
)
