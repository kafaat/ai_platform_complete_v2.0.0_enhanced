"""اختبارات وحدة لأداة حاسبة مساحة المضلّع (polygon_area)."""

from __future__ import annotations

import math

import pytest
from core.agri_tools.tools.polygon_area import compute

pytestmark = pytest.mark.unit


def test_square_near_equator_matches_analytical():
    """مربّع 0.01°×0.01° قرب خطّ الاستواء ≈ المساحة التحليليّة ضمن ~2%."""
    d = 0.01
    lat0 = 0.0
    ring = [
        [44.0, lat0],
        [44.0 + d, lat0],
        [44.0 + d, lat0 + d],
        [44.0, lat0 + d],
    ]
    res = compute(ring)

    R = 6378137.0
    # طول قوس خطّ العرض (شمال-جنوب) ثابت؛ وقوس خطّ الطول يُقاس بـcos(lat).
    dy = math.radians(d) * R
    lat_mid = math.radians(lat0 + d / 2)
    dx = math.radians(d) * R * math.cos(lat_mid)
    expected = dx * dy

    assert math.isclose(res["area_m2"], expected, rel_tol=0.02)
    assert res["vertex_count"] == 4
    # تحقّق سريع من رتبة القيمة (~1.239e6 م²).
    assert 1.20e6 < res["area_m2"] < 1.28e6


def test_repeated_first_point_same_area():
    """تكرار النقطة الأولى في نهاية الحلقة لا يغيّر النتيجة."""
    d = 0.01
    base = [
        [44.0, 15.0],
        [44.0 + d, 15.0],
        [44.0 + d, 15.0 + d],
        [44.0, 15.0 + d],
    ]
    closed = base + [base[0]]

    r_open = compute(base)
    r_closed = compute(closed)

    assert r_open["area_m2"] == r_closed["area_m2"]
    assert r_open["perimeter_m"] == r_closed["perimeter_m"]
    assert r_open["vertex_count"] == r_closed["vertex_count"] == 4


def test_fewer_than_three_points_raises():
    """أقلّ من 3 رؤوس متمايزة يرفع ValueError برسالة عربيّة."""
    with pytest.raises(ValueError, match="مضلّع يحتاج 3 رؤوس على الأقلّ"):
        compute([[44.0, 15.0], [44.001, 15.0]])

    # نقطتان متمايزتان حتّى لو كُرّرت الأولى => لا تزال أقلّ من 3.
    with pytest.raises(ValueError, match="مضلّع يحتاج 3 رؤوس على الأقلّ"):
        compute([[44.0, 15.0], [44.001, 15.0], [44.0, 15.0]])
