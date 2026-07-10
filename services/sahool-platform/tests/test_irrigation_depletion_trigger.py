"""اختبارات: قرار الإطلاق المُشتقّ من استنزاف منطقة الجذور في توصية الريّ (WS-D.1).

الفجوة المُغلَقة: منتِج التوصية (``recommend_irrigation``) كان يحسب الصافي (ETc − مطر)
فقط ويتجاهل الاستنزاف Dr المخزَّن رغم توفّره؛ هذه الاختبارات تُثبِت أنّ Dr + مقابض
السياسة تقودان ``should_irrigate`` و``target_refill_mm`` — مع تدهور صادق عند غياب Dr.
"""

from api.irrigation_policy import IrrigationPolicy
from api.irrigation_recommendation_policy import recommend_irrigation


def _base(**over) -> dict:
    kw = dict(et0_mm=6.0, crop="wheat", stage="mid")
    kw.update(over)
    return recommend_irrigation(**kw)


def test_missing_depletion_fails_safe_no_decision():
    # لا Dr/TAW ⇒ لا قرار إطلاق مُختلَق؛ الصافي يبقى معروضاً.
    out = _base()
    assert out["should_irrigate"] is None
    assert out["trigger_reason"] == "no_depletion_data"
    assert out["target_refill_mm"] is None
    assert out["net_irrigation_mm"] >= 0.0  # الصافي ما زال يُحسب


def test_depletion_at_or_above_trigger_fires_water_saving():
    # WATER_SAVING: trigger_fraction=1.0 ⇒ يُطلق حين Dr ≥ RAW.
    # TAW=100, p=0.5 ⇒ RAW=50. Dr=60 ≥ 50 ⇒ إطلاق.
    out = _base(depletion_mm=60.0, taw_mm=100.0, raw_fraction=0.5, policy="water_saving")
    assert out["should_irrigate"] is True
    assert out["trigger_reason"] == "depletion_at_or_above_trigger"
    assert out["raw_mm"] == 50.0
    # refill_fraction WATER_SAVING = 0.80 ⇒ 0.80×60 = 48.0
    assert out["target_refill_mm"] == 48.0
    assert out["calibrated"] is False


def test_depletion_below_trigger_defers():
    # Dr=40 < RAW=50 ⇒ تأجيل.
    out = _base(depletion_mm=40.0, taw_mm=100.0, raw_fraction=0.5, policy="water_saving")
    assert out["should_irrigate"] is False
    assert out["trigger_reason"] == "defer_below_trigger"
    assert out["target_refill_mm"] == 32.0  # 0.80×40


def test_yield_max_fires_earlier_and_refills_full():
    # YIELD_MAX: trigger_fraction=0.90 ⇒ يُطلق قبل RAW؛ refill=1.00 (ملء كامل).
    # RAW=50, عتبة=0.90×50=45. Dr=46 ≥ 45 ⇒ إطلاق بينما WATER_SAVING كان يؤجّل.
    ws = _base(depletion_mm=46.0, taw_mm=100.0, raw_fraction=0.5, policy="water_saving")
    ym = _base(depletion_mm=46.0, taw_mm=100.0, raw_fraction=0.5, policy="yield_max")
    assert ws["should_irrigate"] is False  # 46 < 50
    assert ym["should_irrigate"] is True  # 46 ≥ 45
    assert ym["target_refill_mm"] == 46.0  # 1.00×46 (ملء كامل)
    assert ym["policy_knobs"]["policy"] == "yield_max"


def test_critical_stress_class_raises_urgency_high():
    out = _base(depletion_mm=90.0, taw_mm=100.0, raw_fraction=0.5, water_stress_class="critical")
    assert out["urgency"] == "high"
    assert out["water_stress_class"] == "critical"


def test_watch_stress_class_lifts_low_urgency_to_moderate():
    # حقل مريح رطوبةً (urgency=none/low من الأساس) لكن الحالة الكنسيّة watch ⇒ moderate.
    out = _base(
        et0_mm=1.0,
        depletion_mm=55.0,
        taw_mm=100.0,
        raw_fraction=0.5,
        water_stress_class="watch",
        soil_moisture_pct=40.0,
    )
    assert out["urgency"] == "moderate"


def test_invalid_taw_fails_safe():
    # TAW=0 ⇒ لا قسمة/قرار (fail-safe).
    out = _base(depletion_mm=60.0, taw_mm=0.0)
    assert out["should_irrigate"] is None
    assert out["trigger_reason"] == "no_depletion_data"


def test_policy_knobs_reported_for_audit():
    out = _base(depletion_mm=60.0, taw_mm=100.0, policy=IrrigationPolicy.RISK_AVERSE)
    knobs = out["policy_knobs"]
    assert knobs["policy"] == "risk_averse"
    assert knobs["trigger_fraction"] == 0.80  # يُطلق مبكّراً
    assert knobs["refill_fraction"] == 1.00  # ملء كامل
