"""اختبار طبقة المعايرة الإقليميّة اليمنيّة (#382) — بنية نقيّة، لا قيم مُلفَّقة.

يثبت: (أ) الملفّ العامّ = الثوابت الحاليّة بالبناء (سلوك محفوظ)؛ (ب) المناطق الخمس
موجودة وترث العامّ موسومةً validated=False؛ (ج) مفاتيح عربيّة؛ (د) منطقة مجهولة ⇒
العامّ؛ (هـ) لا تجاوزات مُلفَّقة (كلّها فارغة الآن)؛ (و) المعايرة المستقبليّة تضبط
القيمة وvalidated. بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api import calibration as C  # noqa: E402
from api.calibration import all_regions, get_calibration  # noqa: E402


def test_generic_matches_current_constants():
    # المصدر الموحّد: العامّ = الثوابت الحاليّة بالبناء (سلوك محفوظ).
    from api.economic_state import _DEFAULT_PRICE_UNCERTAINTY, _DEFAULT_YIELD_UNCERTAINTY
    from api.nutrient_4r import _UPTAKE_FRACTIONS
    from api.soil_water import _DEFAULT_RAW_FRACTION, _DEFAULT_ROOT_DEPTH_M
    from api.water_balance import FORECAST_INFILTRATION_DEFAULT, KC_DYN_MAX, KC_DYN_MIN

    g = get_calibration(None)
    assert g.region == "_generic"
    assert g.validated is False
    assert g.raw_fraction == _DEFAULT_RAW_FRACTION
    assert g.root_depth_m == _DEFAULT_ROOT_DEPTH_M
    assert g.kc_dyn_min == KC_DYN_MIN
    assert g.kc_dyn_max == KC_DYN_MAX
    assert g.forecast_infiltration == FORECAST_INFILTRATION_DEFAULT
    assert g.uptake_fractions == _UPTAKE_FRACTIONS
    assert g.yield_uncertainty == _DEFAULT_YIELD_UNCERTAINTY
    assert g.price_uncertainty == _DEFAULT_PRICE_UNCERTAINTY


def test_five_yemen_regions_present():
    assert set(all_regions()) == {"jawf", "tihama", "marib", "hadramout", "ibb"}


def test_regions_inherit_generic_unvalidated():
    g = get_calibration(None)
    for r in all_regions():
        prof = get_calibration(r)
        assert prof.region == r
        assert prof.validated is False  # لم تُعايَر بعد
        # ترث القيم العامّة بالضبط (لا تجاوزات مُلفَّقة).
        assert prof.raw_fraction == g.raw_fraction
        assert prof.root_depth_m == g.root_depth_m
        assert prof.uptake_fractions == g.uptake_fractions
        assert any("لم تُعايَر" in n or "قياسات" in n for n in prof.notes_ar)


def test_arabic_region_keys():
    assert get_calibration("الجوف").region == "jawf"
    assert get_calibration("تهامة").region == "tihama"
    assert get_calibration("إب").region == "ibb"


def test_unknown_region_falls_back_to_generic():
    prof = get_calibration("atlantis")
    assert prof.region == "_generic"
    assert prof.validated is False


def test_no_fabricated_overrides_yet():
    # كلّ التجاوزات فارغة الآن (لا أرقام غير مُتحقَّقة).
    assert all(ov == {} for ov in C._REGION_OVERRIDES.values())


def test_future_calibration_sets_value_and_validated(monkeypatch):
    # محاكاة معايرة مأرب لاحقاً ⇒ تضبط القيمة وvalidated=True.
    monkeypatch.setitem(C._REGION_OVERRIDES, "marib", {"raw_fraction": 0.45})
    prof = get_calibration("marib")
    assert prof.raw_fraction == 0.45
    assert prof.validated is True


def test_to_dict_shape():
    d = get_calibration("ibb").to_dict()
    assert set(d) >= {
        "region",
        "region_ar",
        "validated",
        "raw_fraction",
        "root_depth_m",
        "kc_dyn_min",
        "kc_dyn_max",
        "uptake_fractions",
        "yield_uncertainty",
    }
