"""اختبارات مراحل نموّ الموسم (season_phenology) — ربط بطاقة المحصول بحالة موسم.

دالّة نقيّة offline: تحليل المرحلة الحاليّة + Kc الطوريّ + خطّ الزمن + علَم التزهير
+ تحويل اسم المحصول إلى crop_id، مع صدق «المجهول/المتجاوِز ⇒ None».
"""

from datetime import date, timedelta

import pytest
from core.engines.fao56 import kc_for_age
from core.season_phenology import (
    crop_kc_profile,
    current_stage,
    is_reproductive_stage,
    resolve_crop_id,
    season_timeline,
    stage_kc,
    stage_kc_map,
)

# ─── resolve_crop_id: اسم → crop_id ──────────────────────────────────────


def test_resolve_crop_id_direct_and_aliases():
    assert resolve_crop_id("common_bean") == "common_bean"  # crop_id مباشر
    assert resolve_crop_id("فاصولياء") == "common_bean"
    assert resolve_crop_id("فول") == "faba_bean"
    assert resolve_crop_id("عتر") == "pea"  # الاسم المحليّ للبازلاء
    assert resolve_crop_id("Wheat") == "wheat"  # غير حسّاس للحالة


def test_resolve_crop_id_unknown_is_none_no_guess():
    assert resolve_crop_id("durian") is None
    assert resolve_crop_id(None) is None
    assert resolve_crop_id("") is None


# ─── current_stage: مطابقة العمر في حدود المراحل ──────────────────────────


def test_current_stage_matches_day_ranges():
    # الفاصولياء: initial [0,20) · development [20,50) · mid [50,90) · late [90,110).
    assert current_stage("common_bean", 5)["stage"] == "initial"
    assert current_stage("common_bean", 30)["stage"] == "development"
    assert current_stage("common_bean", 60)["stage"] == "mid"
    assert current_stage("common_bean", 100)["stage"] == "late"


def test_current_stage_boundaries_are_half_open():
    # الحدّ الأعلى غير مشمول: يوم 20 ⇒ development لا initial (تطابق [start,end)).
    assert current_stage("common_bean", 20)["stage"] == "development"
    assert current_stage("common_bean", 50)["stage"] == "mid"


def test_current_stage_past_cycle_or_unknown_is_none():
    assert current_stage("common_bean", 200) is None  # تجاوز دورة المحصول
    assert current_stage("common_bean", None) is None
    assert current_stage("cranberry", 30) is None  # cranberry البطاقة الوحيدة بلا phenology
    assert current_stage(None, 30) is None


# ─── stage_kc: Kc الطوريّ (FAO-56) ───────────────────────────────────────


def test_stage_kc_follows_fao56_curve():
    # initial ثابت عند kc_initial (0.40)؛ mid عند الذروة (1.15).
    assert stage_kc("common_bean", 5) == 0.40
    assert stage_kc("common_bean", 60) == 1.15
    # development يرتفع بين القيمتين (تدرّج خطّي) — بين 0.40 و1.15.
    mid_dev = stage_kc("common_bean", 35)
    assert 0.40 < mid_dev < 1.15


def test_stage_kc_unknown_is_none():
    assert stage_kc(None, 30) is None
    assert stage_kc("common_bean", None) is None


# ─── is_reproductive_stage: علَم التزهير (للتصعيد) ────────────────────────


def test_is_reproductive_only_in_mid_stage():
    assert is_reproductive_stage("common_bean", 60) is True  # mid = تزهير/قرون
    assert is_reproductive_stage("common_bean", 5) is False  # initial
    assert is_reproductive_stage("common_bean", 100) is False  # late
    assert is_reproductive_stage("common_bean", None) is False


# ─── season_timeline: تواريخ مطلقة + حالة ────────────────────────────────


def test_timeline_absolute_dates_and_status():
    sow = date(2026, 1, 1)
    # يوم 60 بعد البذار ⇒ نحن في mid؛ initial/development ماضيان، late قادم.
    tl = season_timeline("common_bean", sow, today=sow + timedelta(days=60))
    by = {s["stage"]: s for s in tl}
    assert by["initial"]["status"] == "past"
    assert by["development"]["status"] == "past"
    assert by["mid"]["status"] == "current"
    assert by["late"]["status"] == "upcoming"
    # التواريخ المطلقة = البذار + إزاحة اليوم.
    assert by["mid"]["start_date"] == (sow + timedelta(days=50)).isoformat()
    assert by["late"]["end_date"] == (sow + timedelta(days=110)).isoformat()
    # كل مرحلة تحمل إجراءها المفتاحيّ من البطاقة.
    assert by["mid"]["key_action_ar"]


def test_timeline_empty_when_unknown():
    assert season_timeline(None, date(2026, 1, 1)) == []
    assert season_timeline("common_bean", None) == []
    assert season_timeline("cranberry", date(2026, 1, 1)) == []  # cranberry بلا phenology


# ─── G1: منحنى Kc الرباعيّ FAO-56 (Eq.66) — late يهبط خطّيّاً لا Kc_end لكامل المرحلة ───
# القمح (البطاقة): Kc_ini 0.30 · Kc_mid 1.15 · Kc_end 0.40 · stage_days [15, 25, 50, 30]
# ⇒ initial [0,15] · development (15,40] · mid (40,90] · late (90,120].


@pytest.mark.unit
def test_g1_wheat_stage_boundaries_follow_fao56_curve():
    assert stage_kc("wheat", 0) == 0.30
    assert stage_kc("wheat", 15) == 0.30  # نهاية initial
    assert stage_kc("wheat", 40) == 1.15  # نهاية development = Kc_mid
    assert stage_kc("wheat", 90) == 1.15  # نهاية mid = بداية late = Kc_mid (لا قفزة)
    assert stage_kc("wheat", 120) == 0.40  # الحصاد = Kc_end


@pytest.mark.unit
def test_g1_late_stage_midpoint_is_mean_of_kc_mid_and_kc_end():
    prof = crop_kc_profile("wheat")
    kc_mid_late, _ = kc_for_age(prof, 105)  # منتصف late: 90 + 30/2
    assert kc_mid_late == pytest.approx((prof.kc_mid + prof.kc_end) / 2.0)
    assert stage_kc("wheat", 105) == pytest.approx(0.775, abs=0.006)
    # منتصف development بالمثل = متوسّط Kc_ini وKc_mid.
    kc_mid_dev, _ = kc_for_age(prof, 27.5)
    assert kc_mid_dev == pytest.approx((prof.kc_initial + prof.kc_mid) / 2.0)


@pytest.mark.unit
def test_g1_wheat_day_92_audit_case():
    # العطل المقيس: يوم 92 (أوّل late) أخذ Kc_end=0.40 ⇒ 2.4 مم «منخفض» بدل 6.6 مم «متوسّط».
    assert stage_kc("wheat", 92) == pytest.approx(1.10, abs=0.005)
    # الإسقاط المرحليّ (بلا عمر) = متوسّط الهبوط، لا Kc_end.
    assert stage_kc_map("wheat")["late"] == pytest.approx(0.775)
    assert stage_kc_map("wheat")["late"] != crop_kc_profile("wheat").kc_end


@pytest.mark.unit
def test_g1_curve_monotone_rise_then_fall():
    prof = crop_kc_profile("wheat")
    peak_end = sum(prof.stage_days[:3])
    vals = [kc_for_age(prof, d)[0] for d in range(0, prof.total_season_days + 1)]
    rise, fall = vals[: peak_end + 1], vals[peak_end:]
    assert all(b >= a for a, b in zip(rise, rise[1:], strict=False))
    assert all(b <= a for a, b in zip(fall, fall[1:], strict=False))
    assert all(prof.kc_end <= v <= prof.kc_mid for v in fall)


@pytest.mark.unit
def test_g1_day_outside_season_is_clamped():
    assert stage_kc("wheat", -5) == 0.30  # قبل البذار ⇒ Kc_ini
    assert stage_kc("wheat", 500) == 0.40  # بعد الحصاد ⇒ Kc_end (لا استقراء)
