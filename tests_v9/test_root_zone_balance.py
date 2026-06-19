"""اختبار ميزان ماء منطقة الجذور عبر الزمن (FAO-56 eq.85) — نقيّ حتميّ.

يثبت: (أ) سلسلة معلومة ⇒ يوم الإطلاق والكمّيّة الصحيحة (TAW=100, p=0.5, RAW=50,
ETc=10/يوم ⇒ الإطلاق يوم 4 بكمّيّة 50)؛ (ب) Dr مقصوص في [0, TAW]؛ (ج) المطر
يخفّض Dr والفائض ⇒ تسرّب عميق وdr_end=0؛ (د) الريّ يخفّض Dr؛ (هـ) auto_irrigate
يعيد ضبط Dr؛ (و) الموصى به = 0 حين Dr<RAW؛ (ز) سلسلة فارغة؛ (ح) etc=et0*kc؛
(ط) eff_rain يطابق _effective_rain. نواة بلا شبكة/قاعدة.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.root_zone_balance import (  # noqa: E402
    DayInput,
    root_zone_balance,
)
from api.water_balance import _effective_rain  # noqa: E402


def test_known_series_triggers_at_raw():
    # TAW=100, p=0.5 ⇒ RAW=50. ETc=10/يوم بلا مطر/ريّ ⇒ Dr: 10,20,30,40,50,...
    # يبلغ RAW=50 عند اليوم الرابع (الفهرس 4) ⇒ إطلاق واحد بكمّيّة 50.
    days = [DayInput(et0_mm=20.0, kc=0.5) for _ in range(6)]
    res = root_zone_balance(days, taw_mm=100.0, raw_fraction=0.5)
    assert res.raw_mm == 50.0
    assert res.trigger_days == [4, 5]  # 50 ثمّ 60 (لا ريّ آليّ ⇒ يستمرّ التراكم)
    assert res.days[4].dr_end_mm == 50.0
    assert res.days[4].recommended_irrigation_mm == 50.0
    assert res.days[3].irrigation_triggered is False
    assert res.days[3].recommended_irrigation_mm == 0.0


def test_depletion_clamped_within_taw():
    # ETc كبير بلا تعويض ⇒ Dr لا يتجاوز TAW أبداً.
    days = [DayInput(et0_mm=100.0, kc=1.0) for _ in range(5)]
    res = root_zone_balance(days, taw_mm=80.0, raw_fraction=0.5)
    for d in res.days:
        assert 0.0 <= d.dr_end_mm <= 80.0
    assert res.final_depletion_mm == 80.0


def test_rain_reduces_depletion_and_overflow_deep_percolates():
    # يوم بعجز ثمّ مطر غزير ⇒ Dr يهبط، والفائض فوق السعة الحقليّة ⇒ تسرّب عميق وdr_end=0.
    days = [
        DayInput(et0_mm=20.0, kc=1.0),  # Dr=20
        DayInput(et0_mm=10.0, kc=1.0, rain_mm=100.0),  # مطر فعّال كبير ⇒ فائض
    ]
    res = root_zone_balance(days, taw_mm=100.0, raw_fraction=0.5)
    assert res.days[0].dr_end_mm == 20.0
    assert res.days[1].dr_end_mm == 0.0
    assert res.days[1].deep_perc_mm > 0.0


def test_irrigation_reduces_depletion():
    days = [
        DayInput(et0_mm=20.0, kc=1.0),  # Dr=20
        DayInput(et0_mm=20.0, kc=1.0, irrigation_mm=15.0),  # Dr=20-15+20=25
    ]
    res = root_zone_balance(days, taw_mm=100.0, raw_fraction=0.5)
    assert res.days[1].dr_end_mm == 25.0


def test_auto_irrigate_resets_depletion():
    # نفس السلسلة، لكن auto_irrigate=True ⇒ Dr يُملأ عند كلّ إطلاق فيبدأ اليوم التالي من 0.
    days = [DayInput(et0_mm=20.0, kc=0.5) for _ in range(6)]
    res = root_zone_balance(days, taw_mm=100.0, raw_fraction=0.5, auto_irrigate=True)
    # يبلغ RAW=50 يوم 4 ⇒ يُملأ ⇒ يوم 5 يبدأ من 0 ثمّ +10 ⇒ Dr=10 (لا إطلاق ثانٍ).
    assert res.trigger_days == [4]
    assert res.days[4].dr_end_mm == 0.0
    assert res.days[5].dr_end_mm == 10.0


def test_recommended_zero_below_raw():
    days = [DayInput(et0_mm=10.0, kc=1.0) for _ in range(3)]  # Dr: 10,20,30 < RAW=50
    res = root_zone_balance(days, taw_mm=100.0, raw_fraction=0.5)
    assert res.trigger_days == []
    assert res.total_recommended_irrigation_mm == 0.0
    assert all(d.recommended_irrigation_mm == 0.0 for d in res.days)


def test_empty_days():
    res = root_zone_balance([], taw_mm=100.0, raw_fraction=0.5)
    assert res.days == []
    assert res.trigger_days == []
    assert res.final_depletion_mm == 0.0
    assert res.total_recommended_irrigation_mm == 0.0


def test_initial_depletion_respected():
    res = root_zone_balance(
        [DayInput(et0_mm=10.0, kc=1.0)], taw_mm=100.0, raw_fraction=0.5, initial_depletion_mm=45.0
    )
    # يبدأ من 45 +10 = 55 ≥ RAW 50 ⇒ إطلاق فوريّ.
    assert res.days[0].dr_end_mm == 55.0
    assert res.days[0].irrigation_triggered is True


def test_etc_is_et0_times_kc():
    res = root_zone_balance([DayInput(et0_mm=7.0, kc=1.1)], taw_mm=100.0, raw_fraction=0.5)
    assert res.days[0].etc_mm == pytest.approx(7.7)


def test_eff_rain_matches_canonical_helper():
    res = root_zone_balance(
        [DayInput(et0_mm=5.0, kc=1.0, rain_mm=30.0)], taw_mm=100.0, raw_fraction=0.5
    )
    assert res.days[0].eff_rain_mm == pytest.approx(_effective_rain(30.0))


def test_to_dict_round_trips_keys():
    res = root_zone_balance([DayInput(et0_mm=10.0, kc=1.0)], taw_mm=100.0, raw_fraction=0.5)
    d = res.to_dict()
    assert set(d) >= {
        "taw_mm",
        "raw_mm",
        "trigger_days",
        "total_recommended_irrigation_mm",
        "final_depletion_mm",
        "days",
    }
    assert set(d["days"][0]) >= {
        "day_index",
        "etc_mm",
        "eff_rain_mm",
        "dr_start_mm",
        "dr_end_mm",
        "deep_perc_mm",
        "irrigation_triggered",
        "recommended_irrigation_mm",
    }
