"""اختبارات حلقة تعلّم السياسة (core.policy_learning) — منطق صرف offline.

يتحقّق من: معدّل false-positive مرتفع ⇒ "loosen" + تجاوز مُقترَح صحيح الاتّجاه؛
مفيد دائماً ونادر ⇒ "tighten"؛ تحت MIN_SAMPLES ⇒ "keep" + «بيانات غير كافية»؛
المدخل الفارغ ⇒ نتيجة صادقة فارغة؛ وأنّ خريطة alert_type → مفاتيح العتبة صحيحة.
لا حاجة لقاعدة أو شبكة.
"""

import pytest
from core.policy_learning import (
    _DEFAULT_THRESHOLDS,
    _TYPE_TO_KEYS,
    ADJUST_FRACTION,
    FALSE_POSITIVE_RATE,
    HIGH_USEFUL_RATE,
    MIN_SAMPLES,
    RARE_MAX,
    derive_threshold_adjustments,
)

pytestmark = pytest.mark.unit


def _outcomes(alert_type: str, useful: int, not_useful: int) -> list[dict]:
    """يبني قائمة نتائج: ``useful`` نافعة + ``not_useful`` غير نافعة لنوع واحد."""
    return [{"alert_type": alert_type, "useful": True} for _ in range(useful)] + [
        {"alert_type": alert_type, "useful": False} for _ in range(not_useful)
    ]


def test_high_false_positive_rate_loosens_with_override():
    """نوع بمعدّل عدم تفاعل مرتفع ⇒ "loosen" + تجاوز يقلّل الحسّاسيّة."""
    # 10 نتائج، كلّها غير نافعة ⇒ fp_rate = 100% ≥ FALSE_POSITIVE_RATE.
    res = derive_threshold_adjustments(_outcomes("low_moisture", useful=0, not_useful=10))
    entry = res["per_type"]["low_moisture"]
    assert entry["n"] == 10
    assert entry["useful"] == 0
    assert entry["suggestion"] == "loosen"
    ov = entry["suggested_overrides"]
    assert ov, "loosen يجب أن يحمل تجاوزاً مُقترَحاً"
    # LOW_MOISTURE_SOIL_PCT يُطلِق حين الرطوبة < العتبة ⇒ تقليل الحسّاسيّة = خفض العتبة.
    base_soil = _DEFAULT_THRESHOLDS["LOW_MOISTURE_SOIL_PCT"]
    assert ov["LOW_MOISTURE_SOIL_PCT"] < base_soil
    assert ov["LOW_MOISTURE_SOIL_PCT"] == pytest.approx(round(base_soil * (1 - ADJUST_FRACTION), 1))
    # LOW_MOISTURE_IRRIGATION_MM يُطلِق حين الحاجة ≥ العتبة ⇒ تقليل الحسّاسيّة = رفع.
    base_irr = _DEFAULT_THRESHOLDS["LOW_MOISTURE_IRRIGATION_MM"]
    assert ov["LOW_MOISTURE_IRRIGATION_MM"] > base_irr


def test_ndvi_loosen_raises_threshold():
    """vegetation_stress بمعدّل false-positive مرتفع ⇒ رفع NDVI_DROP_WARN (أقلّ حسّاسيّة)."""
    res = derive_threshold_adjustments(_outcomes("vegetation_stress", useful=1, not_useful=9))
    entry = res["per_type"]["vegetation_stress"]
    assert entry["suggestion"] == "loosen"
    base = _DEFAULT_THRESHOLDS["NDVI_DROP_WARN"]
    assert entry["suggested_overrides"]["NDVI_DROP_WARN"] > base
    assert entry["suggested_overrides"]["NDVI_DROP_WARN"] <= 1.0


def test_mostly_useful_and_rare_tightens():
    """نافع دائماً تقريباً ونادر ⇒ "tighten" + تجاوز يزيد الحسّاسيّة."""
    # 9 نافعة + 0 غير نافعة ⇒ useful_rate=100% ≥ HIGH_USEFUL_RATE، n=9 ≤ RARE_MAX.
    assert MIN_SAMPLES <= 9 <= RARE_MAX
    res = derive_threshold_adjustments(_outcomes("frost_risk", useful=9, not_useful=0))
    entry = res["per_type"]["frost_risk"]
    assert entry["useful_rate"] >= HIGH_USEFUL_RATE
    assert entry["suggestion"] == "tighten"
    base = _DEFAULT_THRESHOLDS["FROST_RISK_TMIN_C"]
    # FROST_RISK_TMIN_C يُطلِق حين الحرارة ≤ العتبة ⇒ زيادة الحسّاسيّة = رفع العتبة.
    assert entry["suggested_overrides"]["FROST_RISK_TMIN_C"] > base


def test_mixed_useful_rate_keeps():
    """معدّل تفاعل ضمن النطاق (لا مرتفع false-positive ولا شبه مثاليّ) ⇒ "keep"."""
    # 6 نافعة + 4 غير نافعة ⇒ fp_rate=40% < 60%، useful_rate=60% < 90% ⇒ keep.
    res = derive_threshold_adjustments(_outcomes("heat_stress", useful=6, not_useful=4))
    entry = res["per_type"]["heat_stress"]
    assert entry["suggestion"] == "keep"
    assert entry["suggested_overrides"] == {}


def test_below_min_samples_keeps_insufficient():
    """تحت MIN_SAMPLES ⇒ "keep" + «بيانات غير كافية» مهما كان المعدّل (صدق)."""
    n = MIN_SAMPLES - 1
    res = derive_threshold_adjustments(_outcomes("heavy_rain", useful=0, not_useful=n))
    entry = res["per_type"]["heavy_rain"]
    assert entry["n"] == n
    assert entry["suggestion"] == "keep"
    assert entry["suggested_overrides"] == {}
    assert "بيانات غير كافية" in entry["rationale_ar"]


def test_empty_outcomes_is_honest_empty():
    """مدخل فارغ ⇒ per_type فارغ + ملاحظة صادقة، دون رفع."""
    res = derive_threshold_adjustments([])
    assert res["per_type"] == {}
    assert res["min_samples"] == MIN_SAMPLES
    assert res["false_positive_rate"] == FALSE_POSITIVE_RATE
    assert "لا نتائج" in res["note_ar"]


def test_malformed_outcomes_ignored():
    """نتائج مُشوّهة (بلا alert_type نصّيّ) تُتجاهَل بهدوء — لا رفع."""
    bad = [
        {"useful": True},
        {"alert_type": "", "useful": True},
        {"alert_type": None, "useful": False},
        "not-a-dict",
        {"alert_type": "low_moisture", "useful": False},
    ]
    res = derive_threshold_adjustments(bad)
    # نوع صالح واحد فقط بُنِيَ منه عدّاد (n=1).
    assert set(res["per_type"]) == {"low_moisture"}
    assert res["per_type"]["low_moisture"]["n"] == 1


def test_alert_type_to_threshold_key_mapping():
    """خريطة alert_type → مفاتيح العتبة تطابق ما توثّقه الوحدة وثَبات المفاتيح."""
    assert _TYPE_TO_KEYS["low_moisture"] == (
        "LOW_MOISTURE_SOIL_PCT",
        "LOW_MOISTURE_IRRIGATION_MM",
    )
    assert _TYPE_TO_KEYS["heavy_rain"] == ("HEAVY_RAIN_MM",)
    assert _TYPE_TO_KEYS["heat_stress"] == ("HEAT_STRESS_TMAX_C",)
    assert _TYPE_TO_KEYS["frost_risk"] == ("FROST_RISK_TMIN_C",)
    assert _TYPE_TO_KEYS["vegetation_stress"] == ("NDVI_DROP_WARN",)
    # disease_risk بلا عتبة رقميّة قابلة للضبط ⇒ لا تجاوز حتى عند false-positive مرتفع.
    assert _TYPE_TO_KEYS["disease_risk"] == ()
    res = derive_threshold_adjustments(_outcomes("disease_risk", useful=0, not_useful=10))
    entry = res["per_type"]["disease_risk"]
    assert entry["suggestion"] == "loosen"
    assert entry["suggested_overrides"] == {}
    assert entry["threshold_keys"] == []


def test_threshold_keys_reported_per_type():
    """كلّ مدخل يحمل threshold_keys مطابقة للخريطة (لإبراز ما قد يتأثّر)."""
    res = derive_threshold_adjustments(_outcomes("heavy_rain", useful=3, not_useful=3))
    assert res["per_type"]["heavy_rain"]["threshold_keys"] == ["HEAVY_RAIN_MM"]


def test_defaults_match_alert_rules_thresholds():
    """افتراضات الوحدة النقيّة تطابق AlertThresholds الحقيقيّة (حارس انحراف)."""
    from api.alert_rules import AlertThresholds

    t = AlertThresholds()
    for key, val in _DEFAULT_THRESHOLDS.items():
        assert getattr(t, key) == val, f"انحراف افتراض {key} عن AlertThresholds"
