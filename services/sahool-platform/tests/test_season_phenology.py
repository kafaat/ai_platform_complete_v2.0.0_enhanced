"""اختبارات مراحل نموّ الموسم (season_phenology) — ربط بطاقة المحصول بحالة موسم.

دالّة نقيّة offline: تحليل المرحلة الحاليّة + Kc الطوريّ + خطّ الزمن + علَم التزهير
+ تحويل اسم المحصول إلى crop_id، مع صدق «المجهول/المتجاوِز ⇒ None».
"""

from datetime import date, timedelta

from core.season_phenology import (
    current_stage,
    is_reproductive_stage,
    resolve_crop_id,
    season_timeline,
    stage_kc,
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
    assert current_stage("wheat", 30) is None  # القمح بلا كتلة phenology بعد
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
    assert season_timeline("wheat", date(2026, 1, 1)) == []  # لا phenology للقمح بعد
