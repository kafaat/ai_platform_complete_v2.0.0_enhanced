"""اختبار تقييم جودة المدخلات (Source-of-Truth Honesty) — نقيّ حتميّ.

يثبت: (أ) حقول منظَّمة (confidence/data_quality/assumptions/assumptions_ar)؛ (ب)
الجزاءات تخفض الثقة؛ (ج) uncalibrated_model يمنع «high» دائماً؛ (د) أرضيّة 0.30؛
(هـ) تجاهل المجهول وإزالة التكرار؛ (و) تطابق الرموز ووصفها العربيّ. بلا شبكة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.data_quality import ASSUMPTION_LABELS_AR, assess_data_quality  # noqa: E402


def test_structured_fields_present():
    q = assess_data_quality(["uncalibrated_model", "no_moisture_sensor"])
    assert set(q) == {"confidence", "data_quality", "assumptions", "assumptions_ar", "calibrated"}
    assert q["calibrated"] is False
    assert isinstance(q["confidence"], float)


def test_baseline_uncalibrated_is_medium_never_high():
    # أفضل حالة (تربة وعمق معروفان) تبقى uncalibrated + بلا حسّاس ⇒ medium لا high.
    q = assess_data_quality(["uncalibrated_model", "no_moisture_sensor"])
    assert q["confidence"] == pytest.approx(0.70)
    assert q["data_quality"] == "medium"


def test_more_assumptions_lower_confidence_and_quality():
    q = assess_data_quality(
        ["uncalibrated_model", "no_moisture_sensor", "default_soil", "estimated_root_depth"]
    )
    assert q["confidence"] == pytest.approx(0.47)
    assert q["data_quality"] == "low"


def test_confidence_floored():
    q = assess_data_quality(list(ASSUMPTION_LABELS_AR.keys()) * 3)  # كلّ الجزاءات مكرّرة
    assert q["confidence"] >= 0.30


def test_unknown_codes_ignored_and_deduped():
    q = assess_data_quality(["uncalibrated_model", "uncalibrated_model", "bogus_code"])
    assert q["assumptions"] == ["uncalibrated_model"]  # مزال التكرار، تجوهل المجهول
    assert "bogus_code" not in q["assumptions"]


def test_assumptions_ar_matches_codes():
    q = assess_data_quality(["default_soil", "estimated_root_depth"])
    assert q["assumptions_ar"] == [
        ASSUMPTION_LABELS_AR["default_soil"],
        ASSUMPTION_LABELS_AR["estimated_root_depth"],
    ]


def test_empty_assumptions_full_confidence():
    q = assess_data_quality([])
    assert q["confidence"] == 1.0
    assert q["data_quality"] == "high"
    assert q["assumptions"] == []
