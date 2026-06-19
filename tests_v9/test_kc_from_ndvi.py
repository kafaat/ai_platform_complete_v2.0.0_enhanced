"""اختبار Kc الديناميكيّ من NDVI (مركز المحاصيل، فجوة 2/3).

يثبت: (أ) السلوك المحفوظ — NDVI غائب ⇒ Kc الثابت بالمرحلة حرفيّاً؛ (ب) NDVI متاح ⇒
Kc ضمن نطاق معقول رتيب مع NDVI؛ (ج) القصّ. نواة نقيّة بلا خدمات.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.water_balance import (  # noqa: E402
    KC_BY_CROP_STAGE,
    KC_DYN_MAX,
    KC_DYN_MIN,
    WeatherInput,
    kc_from_ndvi,
    water_balance,
)

_WHEAT = KC_BY_CROP_STAGE["wheat"]


def test_none_ndvi_preserves_static_kc():
    # السلوك المحفوظ: بلا NDVI ⇒ Kc الثابت بالمرحلة تماماً.
    for stage, expected in _WHEAT.items():
        kc, fapar = kc_from_ndvi(None, _WHEAT, stage)
        assert kc == expected
        assert fapar is None
    # مرحلة مجهولة ⇒ 1.0 (السلوك السابق).
    assert kc_from_ndvi(None, _WHEAT, "unknown")[0] == 1.0


def test_ndvi_gives_dynamic_kc_in_range_and_monotonic():
    vals = [kc_from_ndvi(n, _WHEAT, "mid")[0] for n in (0.2, 0.5, 0.8)]
    for kc in vals:
        assert KC_DYN_MIN <= kc <= KC_DYN_MAX
    assert vals[0] < vals[1] < vals[2]  # رتابة مع NDVI


def test_fapar_edges():
    # NDVI منخفض جدّاً (fAPAR=0) ⇒ Kc ≈ الابتدائيّ؛ مرتفع (fAPAR=1) ⇒ ≈ الذرويّ.
    kc_low, f_low = kc_from_ndvi(0.0, _WHEAT, "mid")
    assert f_low == 0.0
    assert abs(kc_low - _WHEAT["initial"]) < 1e-9
    kc_high, f_high = kc_from_ndvi(1.0, _WHEAT, "mid")
    assert f_high == 1.0
    assert abs(kc_high - _WHEAT["mid"]) < 1e-9


def test_water_balance_none_ndvi_matches_static():
    w = WeatherInput(t_min_c=18.0, t_max_c=34.0)
    r_static = water_balance(w, "wheat", "mid", rain_mm=0.0)
    assert r_static.kc == _WHEAT["mid"]  # 1.15
    # مع NDVI ⇒ Kc يختلف + المصدر يذكر «ديناميكيّ».
    r_dyn = water_balance(w, "wheat", "mid", rain_mm=0.0, ndvi=0.7)
    assert r_dyn.kc != _WHEAT["mid"]
    assert "ديناميكيّ" in r_dyn.kc_source_ar
