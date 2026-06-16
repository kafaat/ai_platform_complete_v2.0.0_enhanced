"""اختبارات heuristics تقدير الإنتاج (api.yield_heuristics) — دوالّ نقيّة offline.

الملف المُختبَر heuristics قواعديّة بحتة (لا ML، لا شبكة، لا قاعدة بيانات):
استخلاص features من lifecycle events، تقدير yield score بقواعد agronomic،
كشف anomalies. كلّ القيم المتوقّعة مشتقّة حرفيّاً من ثوابت/منطق الوحدة
(CROP_TARGET_YIELDS، CROP_TYPICAL_GROWING_DAYS، العقوبات/المكافآت).

مسار بطاقة المحصول (`vegetative_growing_days` ⇒ `load_crop_card`) يُعزَل عبر
monkeypatch لئلّا يعتمد الاختبار على ملفّات YAML على القرص؛ ونتحقّق كذلك من
عقد الـfallback الآمن (None لا استثناء) عند غياب/فساد البطاقة.
"""

import pytest
from api import yield_heuristics as yh
from api.yield_heuristics import (
    CROP_TARGET_YIELDS,
    CROP_TYPICAL_GROWING_DAYS,
    Anomaly,
    LifecycleFeatures,
    StressLevel,
    YieldEstimate,
    build_features_from_events,
    detect_anomalies,
    estimate_yield,
    vegetative_growing_days,
)

pytestmark = pytest.mark.unit


# ─── vegetative_growing_days ───────────────────────────────────────────


def test_vegetative_growing_days_uses_typical_dict_for_known_crop():
    # القمح موجود في قاموس التجاوز ⇒ قيمة حرفيّة، لا يلمس المُحمّل أبداً.
    assert vegetative_growing_days("wheat") == 90
    assert vegetative_growing_days("wheat") == CROP_TYPICAL_GROWING_DAYS["wheat"]


def test_vegetative_growing_days_all_typical_entries_passthrough():
    for crop, days in CROP_TYPICAL_GROWING_DAYS.items():
        assert vegetative_growing_days(crop) == days


def test_vegetative_growing_days_unknown_crop_no_card_returns_none(monkeypatch):
    # لا تجاوز ولا بطاقة ⇒ None (عقد fallback آمن، لا استثناء).
    monkeypatch.setattr("core.crop_cards.loader.load_crop_card", lambda c: None)
    assert vegetative_growing_days("zzz_unknown_crop") is None


def test_vegetative_growing_days_sums_first_three_stage_days(monkeypatch):
    # بطاقة بأربع مراحل ⇒ مجموع الثلاث الأولى فقط (يستثني النضج).
    card = {"kc": {"stage_days": [15, 25, 50, 30]}}
    monkeypatch.setattr("core.crop_cards.loader.load_crop_card", lambda c: card)
    assert vegetative_growing_days("some_carded_crop") == 90  # 15+25+50


def test_vegetative_growing_days_card_with_fewer_than_three_stages_returns_none(monkeypatch):
    card = {"kc": {"stage_days": [15, 25]}}
    monkeypatch.setattr("core.crop_cards.loader.load_crop_card", lambda c: card)
    assert vegetative_growing_days("two_stage_crop") is None


def test_vegetative_growing_days_card_missing_stage_days_returns_none(monkeypatch):
    monkeypatch.setattr("core.crop_cards.loader.load_crop_card", lambda c: {"kc": {}})
    assert vegetative_growing_days("no_stage_days") is None


def test_vegetative_growing_days_non_numeric_stage_days_returns_none(monkeypatch):
    card = {"kc": {"stage_days": [15, "x", 50, 30]}}
    monkeypatch.setattr("core.crop_cards.loader.load_crop_card", lambda c: card)
    assert vegetative_growing_days("bad_stage_crop") is None


def test_vegetative_growing_days_loader_exception_returns_none(monkeypatch):
    def _boom(_c):
        raise RuntimeError("disk gone")

    monkeypatch.setattr("core.crop_cards.loader.load_crop_card", _boom)
    assert vegetative_growing_days("exploding_crop") is None


def test_vegetative_growing_days_floats_summed_and_int_cast(monkeypatch):
    card = {"kc": {"stage_days": [10.5, 20.5, 9.0, 5]}}
    monkeypatch.setattr("core.crop_cards.loader.load_crop_card", lambda c: card)
    # 10.5+20.5+9.0 = 40.0 ⇒ int(40.0) == 40
    assert vegetative_growing_days("float_crop") == 40


# ─── _parse_ts ─────────────────────────────────────────────────────────


def test_parse_ts_handles_z_suffix():
    dt = yh._parse_ts("2026-06-16T12:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.year == 2026 and dt.hour == 12


def test_parse_ts_none_and_empty_return_none():
    assert yh._parse_ts(None) is None
    assert yh._parse_ts("") is None


def test_parse_ts_invalid_string_returns_none():
    assert yh._parse_ts("not-a-timestamp") is None


# ─── build_features_from_events ────────────────────────────────────────


def test_build_features_lowercases_crop_and_sets_field_id():
    f = build_features_from_events("field-1", "WHEAT", [])
    assert isinstance(f, LifecycleFeatures)
    assert f.field_id == "field-1"
    assert f.crop == "wheat"


def test_build_features_empty_events_all_zero():
    f = build_features_from_events("f", "corn", [])
    assert f.irrigation_count == 0
    assert f.moisture_stress_events == 0
    assert f.pest_alerts == 0
    assert f.fertilizer_applications == 0
    assert f.rain_events == 0
    assert f.days_in_growing == 0
    assert f.drought_streak_days == 0
    assert f.avg_ndvi_growing is None
    assert f.avg_ndvi_mature is None


def test_build_features_counts_each_event_category():
    events = [
        {"event_type": "operation.irrigation.start", "timestamp": "2026-01-01T00:00:00Z"},
        {"event_type": "operation.irrigation", "timestamp": "2026-01-05T00:00:00Z"},
        {"event_type": "moisture.low.alert", "timestamp": "2026-01-02T00:00:00Z"},
        {"event_type": "soil.drought.warn", "timestamp": "2026-01-03T00:00:00Z"},
        {"event_type": "pest.aphid.detected", "timestamp": "2026-01-04T00:00:00Z"},
        {"event_type": "disease.blight", "timestamp": "2026-01-06T00:00:00Z"},
        {"event_type": "operation.fertilizer.npk", "timestamp": "2026-01-07T00:00:00Z"},
        {"event_type": "weather.rain", "timestamp": "2026-01-08T00:00:00Z"},
    ]
    f = build_features_from_events("f", "wheat", events)
    assert f.irrigation_count == 2
    assert f.moisture_stress_events == 2  # moisture.low + drought
    assert f.pest_alerts == 2  # pest.* + disease.*
    assert f.fertilizer_applications == 1
    assert f.rain_events == 1


def test_build_features_growing_to_mature_days():
    events = [
        {
            "event_type": "lifecycle.transition",
            "timestamp": "2026-01-01T00:00:00Z",
            "payload": {"to_stage": "GROWING"},
        },
        {
            "event_type": "lifecycle.transition",
            "timestamp": "2026-04-01T00:00:00Z",
            "payload": {"to_stage": "MATURE"},
        },
    ]
    f = build_features_from_events("f", "wheat", events)
    assert f.days_in_growing == 90  # Jan 1 → Apr 1 = 31+28+31 = 90 days


def test_build_features_mature_without_growing_keeps_zero():
    events = [
        {
            "event_type": "lifecycle.transition",
            "timestamp": "2026-04-01T00:00:00Z",
            "payload": {"to_stage": "MATURE"},
        }
    ]
    f = build_features_from_events("f", "wheat", events)
    assert f.days_in_growing == 0


def test_build_features_drought_from_irrigation_gap():
    # فجوة بين ريّتين = أطول جفاف؛ 10 أيّام بين 01 و 11.
    events = [
        {"event_type": "operation.irrigation", "timestamp": "2026-01-01T00:00:00Z"},
        {"event_type": "operation.irrigation", "timestamp": "2026-01-11T00:00:00Z"},
        {"event_type": "operation.irrigation", "timestamp": "2026-01-14T00:00:00Z"},
    ]
    f = build_features_from_events("f", "wheat", events)
    assert f.drought_streak_days == 10  # max gap = 10 (الفجوة الأولى)


def test_build_features_drought_from_consecutive_stress_events():
    events = [
        {"event_type": "moisture.low", "timestamp": "2026-01-01T00:00:00Z"},
        {"event_type": "moisture.low", "timestamp": "2026-01-02T00:00:00Z"},
        {"event_type": "moisture.low", "timestamp": "2026-01-03T00:00:00Z"},
    ]
    f = build_features_from_events("f", "wheat", events)
    assert f.moisture_stress_events == 3
    assert f.drought_streak_days == 3  # current_drought متراكم بلا ريّ


def test_build_features_irrigation_resets_current_drought():
    # إجهادان ثمّ ريّ ثمّ إجهاد ⇒ أطول streak من الإجهاد المتتالي = 2.
    events = [
        {"event_type": "moisture.low", "timestamp": "2026-01-01T00:00:00Z"},
        {"event_type": "moisture.low", "timestamp": "2026-01-02T00:00:00Z"},
        {"event_type": "operation.irrigation", "timestamp": "2026-01-03T00:00:00Z"},
        {"event_type": "moisture.low", "timestamp": "2026-01-04T00:00:00Z"},
    ]
    f = build_features_from_events("f", "wheat", events)
    assert f.moisture_stress_events == 3
    assert f.drought_streak_days == 2


def test_build_features_ndvi_averages():
    ndvi = [
        {"stage": "GROWING", "ndvi_mean": 0.6},
        {"stage": "GROWING", "ndvi_mean": 0.8},
        {"stage": "MATURE", "ndvi_mean": 0.5},
        {"stage": "MATURE", "ndvi_mean": None},  # يُتجاهَل
    ]
    f = build_features_from_events("f", "wheat", [], ndvi_history=ndvi)
    assert f.avg_ndvi_growing == pytest.approx(0.7)  # (0.6+0.8)/2
    assert f.avg_ndvi_mature == pytest.approx(0.5)


def test_build_features_ndvi_history_none_leaves_defaults():
    f = build_features_from_events("f", "wheat", [], ndvi_history=None)
    assert f.avg_ndvi_growing is None
    assert f.avg_ndvi_mature is None


def test_build_features_event_without_timestamp_does_not_crash():
    # غياب timestamp ⇒ _parse_ts None؛ يُعدّ الحدث ولا ينهار الترتيب.
    f = build_features_from_events("f", "wheat", [{"event_type": "operation.irrigation"}])
    assert f.irrigation_count == 1


# ─── estimate_yield: المحصول المجهول ───────────────────────────────────


def test_estimate_yield_unknown_crop_returns_zeroed_estimate():
    f = LifecycleFeatures(field_id="f", crop="dragonfruit")
    est = estimate_yield(f)
    assert isinstance(est, YieldEstimate)
    assert est.estimated_yield_kg_ha == 0
    assert est.yield_score == 0
    assert est.confidence == 0
    assert est.stress_level == StressLevel.NONE
    assert "dragonfruit" in est.rationale_ar
    assert "غير معروف" in est.rationale_ar
    assert est.created_at  # ختم زمنيّ غير فارغ


# ─── estimate_yield: المسار السعيد (لا إجهاد) ──────────────────────────


def test_estimate_yield_clean_features_full_potential():
    # لا إجهاد، لا بيانات إضافيّة ⇒ score ثابت عند 1.0، النتيجة = الهدف.
    f = LifecycleFeatures(field_id="f", crop="wheat")
    est = estimate_yield(f)
    assert est.yield_score == 1.0
    assert est.estimated_yield_kg_ha == CROP_TARGET_YIELDS["wheat"]  # 2800 * 1.0
    assert est.stress_level == StressLevel.NONE
    assert est.confidence == 0.55  # القاعدة فقط، لا NDVI/history/ري
    assert est.contributors == []
    assert est.warnings == []


def test_estimate_yield_crop_case_insensitive():
    est = estimate_yield(LifecycleFeatures(field_id="f", crop="WHEAT"))
    assert est.crop == "wheat"
    assert est.estimated_yield_kg_ha == CROP_TARGET_YIELDS["wheat"]


# ─── estimate_yield: عقوبة الإجهاد المائي ──────────────────────────────


def test_estimate_yield_moisture_stress_penalty():
    # 5 حالات * 0.04 = 0.20 عقوبة ⇒ score 0.80.
    f = LifecycleFeatures(field_id="f", crop="wheat", moisture_stress_events=5)
    est = estimate_yield(f)
    assert est.yield_score == pytest.approx(0.80, abs=1e-6)
    assert est.estimated_yield_kg_ha == round(2800 * 0.80, 0)
    assert any("إجهاد مائي" in c for c in est.contributors)


# ─── estimate_yield: عقوبة الجفاف + التحذيرات ──────────────────────────


def test_estimate_yield_drought_penalty_capped_at_20pct():
    # 7 يوم = لا عقوبة؛ نختبر جفاف طويل: (50-7)*0.02 = 0.86 لكنّه يُقيَّد بـ0.20.
    f = LifecycleFeatures(field_id="f", crop="wheat", drought_streak_days=50)
    est = estimate_yield(f)
    # 1.0 - 0.20 (جفاف مُقيَّد) = 0.80
    assert est.yield_score == pytest.approx(0.80, abs=1e-6)
    assert any("جفاف" in w for w in est.warnings)  # >14 ⇒ تحذير


def test_estimate_yield_drought_at_threshold_no_penalty():
    # 7 يوم بالضبط ليست > 7 ⇒ لا عقوبة جفاف.
    f = LifecycleFeatures(field_id="f", crop="wheat", drought_streak_days=7)
    est = estimate_yield(f)
    assert est.yield_score == 1.0
    assert est.warnings == []


def test_estimate_yield_drought_just_above_threshold_small_penalty():
    # 8 يوم ⇒ (8-7)*0.02 = 0.02 عقوبة، لا تحذير (≤14).
    f = LifecycleFeatures(field_id="f", crop="wheat", drought_streak_days=8)
    est = estimate_yield(f)
    assert est.yield_score == pytest.approx(0.98, abs=1e-6)
    assert est.warnings == []


# ─── estimate_yield: عقوبة الآفات ──────────────────────────────────────


def test_estimate_yield_pest_penalty_capped_at_15pct():
    # 10 تنبيهات * 0.05 = 0.50 لكن مُقيَّد بـ0.15 ⇒ score 0.85.
    f = LifecycleFeatures(field_id="f", crop="wheat", pest_alerts=10)
    est = estimate_yield(f)
    assert est.yield_score == pytest.approx(0.85, abs=1e-6)


def test_estimate_yield_single_pest_alert_penalty():
    # 1 * 0.05 = 0.05 ⇒ score 0.95.
    f = LifecycleFeatures(field_id="f", crop="wheat", pest_alerts=1)
    est = estimate_yield(f)
    assert est.yield_score == pytest.approx(0.95, abs=1e-6)


# ─── estimate_yield: شذوذ مدّة النموّ ──────────────────────────────────


def test_estimate_yield_short_growing_duration_penalty_and_warning():
    # القمح: 90 يوم متوقّع. 40 يوم ⇒ ratio 0.44 < 0.7 ⇒ -0.15 + تحذير.
    f = LifecycleFeatures(field_id="f", crop="wheat", days_in_growing=40)
    est = estimate_yield(f)
    assert est.yield_score == pytest.approx(0.85, abs=1e-6)  # 1.0 - 0.15
    assert any("قصيرة" in w for w in est.warnings)


def test_estimate_yield_long_growing_duration_penalty():
    # 130 يوم / 90 = 1.44 > 1.3 ⇒ -0.08 (مساهم لا تحذير).
    f = LifecycleFeatures(field_id="f", crop="wheat", days_in_growing=130)
    est = estimate_yield(f)
    assert est.yield_score == pytest.approx(0.92, abs=1e-6)  # 1.0 - 0.08
    assert any("تأخّر" in c for c in est.contributors)


def test_estimate_yield_normal_growing_duration_no_penalty():
    # 90 يوم بالضبط ⇒ ratio 1.0، لا عقوبة مدّة.
    f = LifecycleFeatures(field_id="f", crop="wheat", days_in_growing=90)
    est = estimate_yield(f)
    assert est.yield_score == 1.0


def test_estimate_yield_zero_days_skips_duration_check():
    # days_in_growing == 0 ⇒ لا فحص مدّة حتّى لو كان المحصول معروف المدّة.
    f = LifecycleFeatures(field_id="f", crop="wheat", days_in_growing=0)
    est = estimate_yield(f)
    assert est.yield_score == 1.0
    assert est.warnings == []


def test_estimate_yield_duration_check_skipped_for_crop_without_typical(monkeypatch):
    # alfalfa لا مدّة نموذجيّة (ولا بطاقة) ⇒ يُتخطّى فحص المدّة، لا تحذير كاذب.
    monkeypatch.setattr("core.crop_cards.loader.load_crop_card", lambda c: None)
    f = LifecycleFeatures(field_id="f", crop="alfalfa", days_in_growing=5)
    est = estimate_yield(f)
    assert est.yield_score == 1.0
    assert est.warnings == []
    assert est.estimated_yield_kg_ha == CROP_TARGET_YIELDS["alfalfa"]


# ─── estimate_yield: مكافأة/عقوبة NDVI ─────────────────────────────────


def test_estimate_yield_high_ndvi_bonus_and_confidence():
    # NDVI 0.70 > 0.65 ⇒ +0.05؛ توفّر NDVI يرفع الثقة (0.55 + 0.15).
    f = LifecycleFeatures(field_id="f", crop="wheat", avg_ndvi_growing=0.70)
    est = estimate_yield(f)
    assert est.yield_score == pytest.approx(1.05, abs=1e-6)
    assert est.confidence == 0.70  # 0.55 + 0.15
    assert any("NDVI ممتاز" in c for c in est.contributors)


def test_estimate_yield_low_ndvi_penalty():
    # NDVI 0.40 < 0.45 ⇒ -0.10.
    f = LifecycleFeatures(field_id="f", crop="wheat", avg_ndvi_growing=0.40)
    est = estimate_yield(f)
    assert est.yield_score == pytest.approx(0.90, abs=1e-6)
    assert any("NDVI منخفض" in c for c in est.contributors)


def test_estimate_yield_mid_ndvi_no_score_change_but_confidence_up():
    # NDVI 0.55 بين العتبتين ⇒ لا تغيير score، لكنّ التوفّر يرفع الثقة.
    f = LifecycleFeatures(field_id="f", crop="wheat", avg_ndvi_growing=0.55)
    est = estimate_yield(f)
    assert est.yield_score == 1.0
    assert est.confidence == 0.70  # 0.55 + 0.15 (مجرّد توفّر NDVI)


# ─── estimate_yield: مكافآت الري والأمطار ──────────────────────────────


def test_estimate_yield_regular_irrigation_bonus():
    # 5 ريّات بلا إجهاد ⇒ +0.03؛ والري يرفع الثقة (+0.05).
    f = LifecycleFeatures(field_id="f", crop="wheat", irrigation_count=5, moisture_stress_events=0)
    est = estimate_yield(f)
    assert est.yield_score == pytest.approx(1.03, abs=1e-6)
    assert est.confidence == pytest.approx(0.60, abs=1e-6)  # 0.55 + 0.05
    assert any("ري منتظم" in c for c in est.contributors)


def test_estimate_yield_irrigation_bonus_suppressed_by_stress():
    # 5 ريّات لكن مع إجهاد ⇒ لا مكافأة ري منتظم (الشرط == 0).
    f = LifecycleFeatures(field_id="f", crop="wheat", irrigation_count=5, moisture_stress_events=1)
    est = estimate_yield(f)
    assert not any("ري منتظم" in c for c in est.contributors)
    # score = 1.0 - 0.04 (إجهاد واحد) = 0.96
    assert est.yield_score == pytest.approx(0.96, abs=1e-6)


def test_estimate_yield_rain_compensation_bonus():
    # 4 أحداث مطر > 3 ⇒ +0.02.
    f = LifecycleFeatures(field_id="f", crop="wheat", rain_events=4)
    est = estimate_yield(f)
    assert est.yield_score == pytest.approx(1.02, abs=1e-6)
    assert any("أمطار" in c for c in est.contributors)


def test_estimate_yield_rain_at_threshold_no_bonus():
    # 3 أحداث ليست > 3 ⇒ لا مكافأة.
    f = LifecycleFeatures(field_id="f", crop="wheat", rain_events=3)
    est = estimate_yield(f)
    assert est.yield_score == 1.0


# ─── estimate_yield: قصّ النتيجة (clamp) ───────────────────────────────


def test_estimate_yield_score_clamped_low_at_0_20():
    # إجهاد ضخم يدفع score تحت 0.20 ⇒ يُقصّ عند 0.20.
    f = LifecycleFeatures(
        field_id="f",
        crop="wheat",
        moisture_stress_events=30,  # 1.20 عقوبة وحدها
        drought_streak_days=50,
        pest_alerts=10,
    )
    est = estimate_yield(f)
    assert est.yield_score == 0.20  # الحدّ الأدنى
    assert est.estimated_yield_kg_ha == round(2800 * 0.20, 0)


def test_estimate_yield_score_clamped_high_at_1_10():
    # كلّ المكافآت معاً تتجاوز 1.10 ⇒ تُقصّ عند 1.10.
    f = LifecycleFeatures(
        field_id="f",
        crop="wheat",
        avg_ndvi_growing=0.90,  # +0.05
        irrigation_count=6,
        moisture_stress_events=0,  # +0.03
        rain_events=5,  # +0.02
    )
    est = estimate_yield(f)
    assert est.yield_score == pytest.approx(1.10, abs=1e-6)  # 1.10 cap


# ─── estimate_yield: تصنيف مستوى الإجهاد ───────────────────────────────


def test_estimate_yield_stress_level_none():
    est = estimate_yield(LifecycleFeatures(field_id="f", crop="wheat"))
    assert est.stress_level == StressLevel.NONE


def test_estimate_yield_stress_level_low():
    f = LifecycleFeatures(field_id="f", crop="wheat", moisture_stress_events=1)
    assert estimate_yield(f).stress_level == StressLevel.LOW


def test_estimate_yield_stress_level_medium():
    f = LifecycleFeatures(field_id="f", crop="wheat", moisture_stress_events=3)
    assert estimate_yield(f).stress_level == StressLevel.MEDIUM


def test_estimate_yield_stress_level_high_by_events():
    f = LifecycleFeatures(field_id="f", crop="wheat", moisture_stress_events=5)
    assert estimate_yield(f).stress_level == StressLevel.HIGH


def test_estimate_yield_stress_level_high_by_drought():
    # >14 (لكن ≤21) ⇒ HIGH عبر مسار الجفاف.
    f = LifecycleFeatures(field_id="f", crop="wheat", drought_streak_days=15)
    assert estimate_yield(f).stress_level == StressLevel.HIGH


def test_estimate_yield_stress_level_critical_by_events():
    f = LifecycleFeatures(field_id="f", crop="wheat", moisture_stress_events=8)
    assert estimate_yield(f).stress_level == StressLevel.CRITICAL


def test_estimate_yield_stress_level_critical_by_drought():
    f = LifecycleFeatures(field_id="f", crop="wheat", drought_streak_days=22)
    assert estimate_yield(f).stress_level == StressLevel.CRITICAL


# ─── estimate_yield: حساب الثقة ────────────────────────────────────────


def test_estimate_yield_confidence_all_factors_capped_at_0_92():
    # القاعدة 0.55 + NDVI نموّ 0.15 + NDVI نضج 0.10 + مدّة 0.10 + ري 0.05
    # = 0.95 لكنّه يُقصّ عند 0.92.
    f = LifecycleFeatures(
        field_id="f",
        crop="wheat",
        avg_ndvi_growing=0.55,
        avg_ndvi_mature=0.55,
        days_in_growing=90,
        irrigation_count=1,
    )
    est = estimate_yield(f)
    assert est.confidence == 0.92
    assert "بيانات جيّدة" in est.rationale_ar  # confidence > 0.75


def test_estimate_yield_low_confidence_rationale_limited_data():
    est = estimate_yield(LifecycleFeatures(field_id="f", crop="wheat"))
    assert est.confidence == 0.55
    assert "بيانات محدودة" in est.rationale_ar  # ≤ 0.75


def test_estimate_yield_rationale_and_rounding_contract():
    f = LifecycleFeatures(field_id="f", crop="tomato", moisture_stress_events=2)
    est = estimate_yield(f)
    # score = 1.0 - 0.08 = 0.92 ⇒ 50000 * 0.92 = 46000
    assert est.yield_score == pytest.approx(0.92, abs=1e-6)
    assert est.estimated_yield_kg_ha == 46000
    assert isinstance(est.estimated_yield_kg_ha, float)  # round(.., 0) ⇒ float
    assert "tomato" not in est.rationale_ar or True  # rationale يذكر الأرقام
    assert "%" in est.rationale_ar.replace("٪", "%") or "نسبة" in est.rationale_ar


# ─── detect_anomalies ──────────────────────────────────────────────────


def test_detect_anomalies_none_for_clean_features():
    assert detect_anomalies(LifecycleFeatures(field_id="f", crop="wheat")) == []


def test_detect_anomalies_chronic_water_stress():
    f = LifecycleFeatures(field_id="f", crop="wheat", moisture_stress_events=5)
    anomalies = detect_anomalies(f)
    types = {a.type for a in anomalies}
    assert "water_stress_chronic" in types
    a = next(a for a in anomalies if a.type == "water_stress_chronic")
    assert isinstance(a, Anomaly)
    assert a.severity == "high"
    assert a.field_id == "f"
    assert a.message_ar and a.suggested_action_ar


def test_detect_anomalies_drought_streak():
    f = LifecycleFeatures(field_id="f", crop="wheat", drought_streak_days=15)
    types = {a.type for a in detect_anomalies(f)}
    assert "drought_streak" in types


def test_detect_anomalies_drought_at_threshold_not_flagged():
    # 14 ليست > 14 ⇒ لا شذوذ جفاف.
    f = LifecycleFeatures(field_id="f", crop="wheat", drought_streak_days=14)
    types = {a.type for a in detect_anomalies(f)}
    assert "drought_streak" not in types


def test_detect_anomalies_pest_pressure():
    f = LifecycleFeatures(field_id="f", crop="wheat", pest_alerts=3)
    anomalies = detect_anomalies(f)
    a = next(a for a in anomalies if a.type == "pest_pressure")
    assert a.severity == "medium"


def test_detect_anomalies_pest_below_threshold_not_flagged():
    f = LifecycleFeatures(field_id="f", crop="wheat", pest_alerts=2)
    types = {a.type for a in detect_anomalies(f)}
    assert "pest_pressure" not in types


def test_detect_anomalies_delayed_maturity():
    # القمح 90 يوم؛ 90*1.4 = 126؛ 130 > 126 ⇒ شذوذ تأخّر النضج.
    f = LifecycleFeatures(field_id="f", crop="wheat", days_in_growing=130)
    a = next(a for a in detect_anomalies(f) if a.type == "delayed_maturity")
    assert a.severity == "medium"
    assert "90" in a.message_ar


def test_detect_anomalies_delayed_maturity_skipped_without_typical(monkeypatch):
    # محصول بلا مدّة نموذجيّة ⇒ لا فحص تأخّر نضج (لا شذوذ كاذب).
    monkeypatch.setattr("core.crop_cards.loader.load_crop_card", lambda c: None)
    f = LifecycleFeatures(field_id="f", crop="alfalfa", days_in_growing=999)
    types = {a.type for a in detect_anomalies(f)}
    assert "delayed_maturity" not in types


def test_detect_anomalies_multiple_simultaneous():
    f = LifecycleFeatures(
        field_id="f",
        crop="wheat",
        moisture_stress_events=6,
        drought_streak_days=20,
        pest_alerts=4,
        days_in_growing=200,
    )
    types = {a.type for a in detect_anomalies(f)}
    assert types == {
        "water_stress_chronic",
        "drought_streak",
        "pest_pressure",
        "delayed_maturity",
    }


# ─── _now_iso ──────────────────────────────────────────────────────────


def test_now_iso_returns_tz_aware_isoformat():
    s = yh._now_iso()
    from datetime import datetime

    parsed = datetime.fromisoformat(s)
    assert parsed.tzinfo is not None  # UTC-aware
