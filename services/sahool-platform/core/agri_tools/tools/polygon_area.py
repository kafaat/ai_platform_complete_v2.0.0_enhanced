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
    ring = [(float(lon), float(lat)) for lon, lat in coords]
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
    if len(ring) < 3:
        raise ValueError("مضلّع يحتاج 3 رؤوس على الأقلّ")

    # المساحة الكرويّة (Chamberlain & Duquette).
    area = 0.0
    n = len(ring)
    for i in range(n):
        lon1, lat1 = ring[i]
        lon2, lat2 = ring[(i + 1) % n]
        area += math.radians(lon2 - lon1) * (
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
