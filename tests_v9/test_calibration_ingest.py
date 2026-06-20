"""اختبار مسار التحقّق/الإدخال لقيم المعايرة (#382) — نقيّ، لا قيم مُلفَّقة.

يثبت: (أ) قبول قيمة ضمن المدى؛ (ب) رفض خارج المدى بسبب عربيّ؛ (ج) نِسَب امتصاص
تجمع 1.0 مقبولة، 0.7 مرفوضة؛ (د) حقل مجهول مرفوض؛ (هـ) validated=False بلا source_ar
وTrue معه؛ (و) دلالة ready_to_persist؛ (ز) لا تلفيق (حقل غير مُقدَّم غائب عن accepted).
بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.calibration_ingest import validate_region_calibration  # noqa: E402


def test_accept_in_range_raw_fraction():
    out = validate_region_calibration("jawf", {"raw_fraction": 0.5}, source_ar="قياس ميدانيّ")
    assert out["accepted"] == {"raw_fraction": 0.5}
    assert out["rejected"] == []
    assert out["override_block"] == {"raw_fraction": 0.5}
    assert out["region"] == "jawf"


def test_reject_out_of_range_raw_fraction():
    out = validate_region_calibration("jawf", {"raw_fraction": 0.9})
    assert out["accepted"] == {}
    assert len(out["rejected"]) == 1
    rej = out["rejected"][0]
    assert rej["field"] == "raw_fraction"
    assert rej["value"] == 0.9
    assert rej["reason_ar"]  # سبب عربيّ غير فارغ


def test_uptake_fractions_sum_one_accepted():
    uptake = {"initial": 0.1, "development": 0.3, "mid": 0.4, "late": 0.2}
    out = validate_region_calibration("ibb", {"uptake_fractions": uptake})
    assert out["accepted"]["uptake_fractions"] == uptake
    assert out["rejected"] == []


def test_uptake_fractions_sum_off_rejected():
    uptake = {"initial": 0.1, "development": 0.2, "mid": 0.2, "late": 0.2}  # = 0.7
    out = validate_region_calibration("ibb", {"uptake_fractions": uptake})
    assert "uptake_fractions" not in out["accepted"]
    assert any(r["field"] == "uptake_fractions" for r in out["rejected"])


def test_unknown_key_rejected():
    out = validate_region_calibration("marib", {"bogus_field": 1.0})
    assert out["accepted"] == {}
    assert out["rejected"][0]["field"] == "bogus_field"
    assert out["rejected"][0]["reason_ar"] == "حقل غير قابل للمعايرة"


def test_validated_requires_source_ar():
    without = validate_region_calibration("jawf", {"raw_fraction": 0.5})
    assert without["validated"] is False
    with_src = validate_region_calibration("jawf", {"raw_fraction": 0.5}, source_ar="قياس ميدانيّ")
    assert with_src["validated"] is True


def test_validated_false_when_no_accepted_even_with_source():
    out = validate_region_calibration("jawf", {"raw_fraction": 0.9}, source_ar="قياس")
    assert out["accepted"] == {}
    assert out["validated"] is False


def test_ready_to_persist_semantics():
    clean = validate_region_calibration("jawf", {"raw_fraction": 0.5})
    assert clean["ready_to_persist"] is True  # مقبول ولا مرفوض
    mixed = validate_region_calibration("jawf", {"raw_fraction": 0.5, "root_depth_m": 9.0})
    assert mixed["ready_to_persist"] is False  # يوجد مرفوض
    empty = validate_region_calibration("jawf", {})
    assert empty["ready_to_persist"] is False  # لا مقبول


def test_never_fabricates_missing_fields_absent():
    out = validate_region_calibration("jawf", {"raw_fraction": 0.5})
    # حقول لم تُقدَّم يجب ألّا تظهر في accepted/override_block.
    for fld in ("root_depth_m", "kc_dyn_min", "kc_dyn_max", "forecast_infiltration"):
        assert fld not in out["accepted"]
        assert fld not in out["override_block"]
    assert out["calibrated"] is False


def test_kc_min_below_max_both_accepted():
    # كلاهما ضمن المدى وmin < max ⇒ يُقبلان.
    out = validate_region_calibration("jawf", {"kc_dyn_min": 0.4, "kc_dyn_max": 0.9})
    assert out["accepted"]["kc_dyn_min"] == 0.4
    assert out["accepted"]["kc_dyn_max"] == 0.9
    assert out["rejected"] == []
