"""اختبارات تتبّع GDD (api.gdd_tracker) — دوالّ نقيّة offline.

تتحقّق من معادلة الـGDD اليوميّة (max(0, (Tmax+Tmin)/2 − T_base) مع سقف Tmax عند
T_upper)، التراكم عبر سلسلة الأيّام، تحديد المرحلة الحاليّة والتالية والـGDD المتبقّي،
لوحة `stage_progress`، حالة النضج (next_stage=None)، رفع ValueError لمحصول غير معروف،
و`to_dict` (التقريب). كلّ القيم المتوقّعة مُشتقّة من `GDD_CROP_PARAMS` ومن الكود.
"""

import pytest
from api.gdd_tracker import (
    GDD_CROP_PARAMS,
    DailyTemp,
    GDDResult,
    daily_gdd,
    track_gdd,
)

pytestmark = pytest.mark.unit


# ─── daily_gdd: المعادلة والحدود ─────────────────────────────────


def test_daily_gdd_basic_mean_minus_base():
    # (20+10)/2 − 0 = 15.
    assert daily_gdd(10, 20, 0.0) == 15.0


def test_daily_gdd_with_base_subtracts_base():
    # (20+10)/2 − 10 = 5 (محاصيل t_base=10 مثل sorghum/maize).
    assert daily_gdd(10, 20, 10.0) == 5.0


def test_daily_gdd_below_base_floors_to_zero():
    # المتوسّط 1.5 أقلّ من t_base 10 ⇒ max(0, ...) = 0.
    assert daily_gdd(0, 3, 10.0) == 0.0


def test_daily_gdd_exactly_at_base_is_zero():
    # المتوسّط = t_base بالضبط ⇒ 0.
    assert daily_gdd(10, 10, 10.0) == 0.0


def test_daily_gdd_upper_cap_clips_tmax_only():
    # Tmax=40 يُقصّ إلى t_upper=30 ⇒ (30+20)/2 − 10 = 15؛ Tmin لا يُقصّ.
    assert daily_gdd(20, 40, 10.0, 30.0) == 15.0


def test_daily_gdd_no_cap_when_t_upper_none():
    # بلا سقف ⇒ Tmax يُستعمل كما هو: (40+20)/2 − 10 = 20.
    assert daily_gdd(20, 40, 10.0, None) == 20.0


def test_daily_gdd_cap_not_applied_when_tmax_below_upper():
    # Tmax=25 < t_upper=30 ⇒ لا قصّ: (25+15)/2 − 0 = 20.
    assert daily_gdd(15, 25, 0.0, 30.0) == 20.0


def test_daily_gdd_does_not_clip_tmin_at_base():
    # توثيق صريح للسلوك: Tmin لا يُقصّ عند t_base (تعليق الكود يذكر بعض المراجع تقصّه).
    # Tmin=-10 يبقى ضمن المتوسّط: (10 + (−10))/2 − 0 = 0.
    assert daily_gdd(-10, 10, 0.0) == 0.0


# ─── track_gdd: التراكم وتحديد المرحلة ───────────────────────────


def test_track_empty_temps_starts_at_planting():
    r = track_gdd("wheat", [])
    assert r.cumulative_gdd == 0.0
    assert r.days_counted == 0
    assert r.current_stage == "planting"
    # المرحلة التالية = أوّل مرحلة (emergence) والـGDD المتبقّي = عتبتها.
    assert r.next_stage == "emergence"
    assert r.gdd_to_next_stage == 120.0
    assert r.t_base == 0.0


def test_track_accumulates_and_reaches_first_stage():
    # 10 أيّام × 15 GDD = 150 ≥ emergence(120) لكن < tillering(400).
    r = track_gdd("wheat", [DailyTemp(10, 20)] * 10)
    assert r.cumulative_gdd == 150.0
    assert r.current_stage == "emergence"
    assert r.next_stage == "tillering"
    assert r.gdd_to_next_stage == 400 - 150  # = 250
    assert r.days_counted == 10


def test_track_before_first_threshold_stays_planting():
    # 5 أيّام × 15 = 75 < emergence(120) ⇒ ما زال planting، التالي emergence.
    r = track_gdd("wheat", [DailyTemp(10, 20)] * 5)
    assert r.cumulative_gdd == 75.0
    assert r.current_stage == "planting"
    assert r.next_stage == "emergence"
    assert r.gdd_to_next_stage == 120 - 75  # = 45


def test_track_threshold_inclusive_boundary():
    # عتبة شاملة: cumulative == threshold ⇒ المرحلة بُلِغت.
    # 8 أيّام × 15 = 120 = emergence(120) بالضبط.
    r = track_gdd("wheat", [DailyTemp(10, 20)] * 8)
    assert r.cumulative_gdd == 120.0
    assert r.current_stage == "emergence"
    assert r.gdd_to_next_stage == 400 - 120  # = 280


def test_track_maturity_reached_has_no_next_stage():
    # تراكم ضخم يتجاوز maturity(1600) ⇒ next_stage=None و gdd_to_next=None.
    r = track_gdd("wheat", [DailyTemp(20, 40)] * 200)  # سقف 30 ⇒ 25/يوم × 200 = 5000
    assert r.cumulative_gdd == 5000.0
    assert r.current_stage == "maturity"
    assert r.next_stage is None
    assert r.gdd_to_next_stage is None
    assert "النضج" in r.notes_ar


def test_track_intermediate_stage_tillering():
    # نحتاج ≥ 400 و < 900: 30 يوم × 15 = 450 ⇒ tillering، التالي heading.
    r = track_gdd("wheat", [DailyTemp(10, 20)] * 30)
    assert r.cumulative_gdd == 450.0
    assert r.current_stage == "tillering"
    assert r.next_stage == "heading"
    assert r.gdd_to_next_stage == 900 - 450  # = 450


# ─── stage_progress ──────────────────────────────────────────────


def test_stage_progress_reflects_reached_flags():
    r = track_gdd("wheat", [DailyTemp(10, 20)] * 10)  # 150 GDD
    prog = {p["stage"]: p for p in r.stage_progress}
    assert prog["emergence"]["reached"] is True
    assert prog["emergence"]["gdd_threshold"] == 120
    assert prog["tillering"]["reached"] is False
    # كلّ مراحل المحصول مُمثّلة بنفس العدد والترتيب.
    assert [p["stage"] for p in r.stage_progress] == [
        name for name, _ in GDD_CROP_PARAMS["wheat"]["stages"]
    ]


# ─── المحاصيل المختلفة ومعاملاتها ────────────────────────────────


def test_sorghum_uses_its_base_temp():
    # sorghum t_base=10، t_upper=38؛ يوم (15+25)/2 − 10 = 10.
    r = track_gdd("sorghum", [DailyTemp(15, 25)] * 10)
    assert r.t_base == 10.0
    assert r.cumulative_gdd == 100.0  # 10/يوم × 10
    assert r.current_stage == "emergence"  # emergence sorghum = 100


def test_each_crop_has_five_named_stages():
    for crop, params in GDD_CROP_PARAMS.items():
        r = track_gdd(crop, [])
        assert r.crop == crop
        assert len(r.stage_progress) == len(params["stages"]) == 5


# ─── محصول غير معروف ─────────────────────────────────────────────


def test_unknown_crop_raises_value_error():
    with pytest.raises(ValueError) as e:
        track_gdd("banana", [DailyTemp(10, 20)])
    # الرسالة تتضمّن المتاح من المحاصيل (تشخيص graceful).
    assert "banana" in str(e.value)
    assert "wheat" in str(e.value)


# ─── to_dict والتقريب ────────────────────────────────────────────


def test_to_dict_rounds_and_preserves_fields():
    r = track_gdd("wheat", [DailyTemp(10, 20)] * 10)
    d = r.to_dict()
    assert d["crop"] == "wheat"
    assert d["t_base"] == 0.0
    assert d["days_counted"] == 10
    assert d["cumulative_gdd"] == 150.0
    assert d["current_stage"] == "emergence"
    assert d["next_stage"] == "tillering"
    assert d["gdd_to_next_stage"] == 250.0
    assert isinstance(d["stage_progress"], list)
    assert isinstance(d["notes_ar"], str)


def test_to_dict_null_next_stage_when_mature():
    r = track_gdd("wheat", [DailyTemp(20, 40)] * 200)
    d = r.to_dict()
    assert d["next_stage"] is None
    assert d["gdd_to_next_stage"] is None


def test_to_dict_rounds_fractional_gdd():
    # يوم (10.25+20.0)/2 − 0 = 15.125 ⇒ التراكم 15.125 يُقرّب إلى 15.1 في to_dict.
    r = track_gdd("wheat", [DailyTemp(10.25, 20.0)])
    assert r.cumulative_gdd == 15.125
    assert r.to_dict()["cumulative_gdd"] == 15.1


def test_track_returns_gddresult_instance():
    r = track_gdd("wheat", [])
    assert isinstance(r, GDDResult)
