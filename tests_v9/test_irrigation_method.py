"""اختبار أثر طريقة الريّ (#387) — نقيّ حتميّ، كفاءات FAO عامّة موسومة.

يثبت: (أ) ترتيب الكفاءة غمر<مرشّات<محوري<تقطير؛ (ب) الإجماليّ=الصافي÷الكفاءة (الغمر
يسحب أكثر)؛ (ج) التقطير wetted/ke أقلّ؛ (د) مفاتيح عربيّة؛ (هـ) مجهولة ⇒ عامّ + تحذير؛
(و) كفاءة مُمرَّرة تتجاوز الطريقة؛ (ز) calibrated=False. بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.irrigation_method import (  # noqa: E402
    gross_irrigation_mm,
    method_profile,
    normalize_method,
)


def test_efficiency_ordering():
    ea = {
        m: method_profile(m)["application_efficiency"]
        for m in ("flood", "sprinkler", "pivot", "drip")
    }
    assert ea["flood"] < ea["sprinkler"] < ea["pivot"] < ea["drip"]


def test_gross_is_net_over_efficiency():
    # غمر Ea=0.55 ⇒ 55 صافٍ يسحب 100 إجماليّ؛ التقطير 0.90 ⇒ ~61.
    assert gross_irrigation_mm(55.0, "flood") == pytest.approx(100.0, abs=0.1)
    assert gross_irrigation_mm(55.0, "drip") == pytest.approx(61.11, abs=0.1)
    assert gross_irrigation_mm(55.0, "flood") > gross_irrigation_mm(55.0, "drip")


def test_drip_localized_wetting():
    drip = method_profile("drip")
    assert drip["wetted_fraction"] < 1.0  # يبلّل جزءاً
    assert drip["ke_factor"] < 1.0  # تبخّر أقلّ


def test_pressurized_flag():
    assert method_profile("flood")["pressurized"] is False  # جاذبيّ
    assert method_profile("pivot")["pressurized"] is True  # مضغوط


def test_arabic_keys():
    assert normalize_method("تقطير")[0] == "drip"
    assert normalize_method("غمر")[0] == "flood"
    assert normalize_method("محوري")[0] == "pivot"


def test_unknown_method_generic_flagged():
    p = method_profile("space_irrigation")
    assert p["known"] is False
    assert p["method"] == "generic"
    assert any("غير معروفة" in w for w in p["warnings_ar"])


def test_explicit_efficiency_overrides_method():
    # كفاءة مُقاسة تتجاوز افتراضيّ الطريقة.
    assert gross_irrigation_mm(50.0, "flood", application_efficiency=1.0) == pytest.approx(50.0)


def test_calibrated_false():
    assert method_profile("drip")["calibrated"] is False
    assert any("غير معايَرة" in w for w in method_profile("drip")["warnings_ar"])
