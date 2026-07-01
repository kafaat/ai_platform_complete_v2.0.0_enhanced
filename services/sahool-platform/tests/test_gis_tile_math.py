"""تحقّق جغرافيّ — رياضيّات بلاطات slippy-map (Production Hardening — المرحلة B).

يتحقّق أنّ دوالّ تحويل البلاطة ↔ خطّ الطول/العرض في ``api/routers/weather.py``
تطابق صيغة XYZ/WebMercator القياسيّة. هذه الدوالّ تحدّد **أين** تُؤخَذ عيّنات
الطقس داخل كلّ بلاطة، فأيّ انحراف يزيح الطبقة الحراريّة/المطر عن موقعها الحقيقيّ.

المراسي (المعادلات القياسيّة):
- ``_tile_lon(x,z) = x/2^z · 360 − 180`` ⇒ x=0 عند z=0 ⇒ −180°، x=2^z ⇒ +180°.
- ``_tile_lat(y,z) = deg(atan(sinh(π − 2π·y/2^z)))`` ⇒ y=0 عند z=0 ⇒ +85.0511°.
- بلاطة z=0 الوحيدة تغطّي العالم كاملاً؛ مركزها (0,0).
- نقاط الاستيفاء الخمس (nw/ne/sw/se/center) داخل حدود البلاطة دائماً.

منطق فيزيائيّ صرف (وظيفة Platform Unit Tests) — يُستورَد ``api`` من جذر المنصّة.
"""

from __future__ import annotations

from api.routers.weather import (
    _tile_center,
    _tile_interpolation_points,
    _tile_lat,
    _tile_lat_bounds,
    _tile_lon,
    _tile_lon_bounds,
)

_MERC_LAT_CUTOFF = 85.05112878  # حدّ عرض Web Mercator


# ── خطّ الطول: خطّيّ في x ────────────────────────────────────────────────────
def test_tile_lon_spans_world_at_zoom0():
    assert _tile_lon(0, 0) == -180.0  # الحافة الغربيّة للعالم
    assert _tile_lon(1, 0) == 180.0  # x = 2^0 = 1 ⇒ الحافة الشرقيّة


def test_tile_lon_midpoints():
    assert _tile_lon(1, 1) == 0.0  # منتصف العالم عند z=1
    assert _tile_lon(2, 2) == 0.0  # وعند z=2
    assert _tile_lon(1, 2) == -90.0


def test_tile_lon_monotonic_increasing_in_x():
    prev = -999.0
    for x in range(0, 5):
        lon = _tile_lon(x, 2)
        assert lon > prev
        prev = lon


# ── خطّ العرض: عكس Mercator، متناقص في y ─────────────────────────────────────
def test_tile_lat_cutoff_at_zoom0():
    # y=0 ⇒ أقصى شمال Mercator، y=2^z ⇒ أقصى جنوب (متماثلان).
    assert abs(_tile_lat(0, 0) - _MERC_LAT_CUTOFF) < 1e-5
    assert abs(_tile_lat(1, 0) + _MERC_LAT_CUTOFF) < 1e-5


def test_tile_lat_equator_at_center_row():
    assert abs(_tile_lat(1, 1)) < 1e-9  # منتصف الشبكة عند z=1 ⇒ خطّ الاستواء
    assert abs(_tile_lat(2, 2)) < 1e-9


def test_tile_lat_monotonic_decreasing_in_y():
    prev = 999.0
    for y in range(0, 5):
        lat = _tile_lat(y, 2)
        assert lat < prev
        prev = lat


# ── المركز والحدود ───────────────────────────────────────────────────────────
def test_tile_center_of_world_is_origin():
    lat, lon = _tile_center(0, 0, 0)  # يعيد (lat, lon)
    assert abs(lat) < 1e-9 and abs(lon) < 1e-9


def test_tile_bounds_consistency():
    west, east = _tile_lon_bounds(0, 1)
    assert (west, east) == (-180.0, 0.0)
    north, south = _tile_lat_bounds(0, 1)
    assert north > south  # الشمال أعلى من الجنوب دائماً
    # المركز يقع بين الحدود.
    lat, lon = _tile_center(1, 0, 0)
    assert south <= lat <= north and west <= lon <= east


# ── نقاط الاستيفاء ───────────────────────────────────────────────────────────
def test_interpolation_points_shape():
    pts = _tile_interpolation_points(1, 0, 0)
    assert [p["id"] for p in pts] == ["nw", "ne", "sw", "se", "center"]


def test_interpolation_points_inside_tile():
    z, x, y = 3, 4, 2
    west, east = _tile_lon_bounds(x, z)
    north, south = _tile_lat_bounds(y, z)
    for p in _tile_interpolation_points(z, x, y):
        assert south <= p["lat"] <= north, p
        assert west <= p["lon"] <= east, p


def test_interpolation_center_matches_tile_center():
    z, x, y = 2, 1, 1
    center = next(p for p in _tile_interpolation_points(z, x, y) if p["id"] == "center")
    lat, lon = _tile_center(z, x, y)
    assert abs(center["lat"] - lat) < 1e-9 and abs(center["lon"] - lon) < 1e-9
