"""اختبار الحالة الرقميّة الموحّدة للمحصول (Crop Digital Twin State) — نقيّ حتميّ.

يثبت أنّ التوأم **يركّب** الوحدات بأمانة دون اختراع حالة جديدة:
(أ) الفينولوجيا: GDD ⇒ تقدّم ⇒ مرحلة؛ (ب) past_maturity حين يتجاوز GDD النضج؛
(ج) الماء يطابق root_zone_balance؛ (د) العناصر تطابق nutrient_uptake عند التقدّم؛
(هـ) محصول مجهول ⇒ علم + معاملات عامّة؛ (و) calibrated=False؛ (ز) سلسلة فارغة
تحترم initial_depletion؛ (ح) auto_irrigate ينعكس في الحالة. نواة بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.crop_twin import TwinDay, crop_twin_state  # noqa: E402
from api.nutrient_4r import nutrient_uptake  # noqa: E402
from api.root_zone_balance import DayInput, root_zone_balance  # noqa: E402


def _wheat_days(n, et0=20.0, kc=0.5):
    # wheat: t_base=0, t_cap=30 ⇒ يوم 10/30 = GDD 20.
    return [TwinDay(t_min_c=10.0, t_max_c=30.0, et0_mm=et0, kc=kc) for _ in range(n)]


def test_phenology_progress_and_stage():
    # 10 أيّام × GDD 20 = 200؛ wheat نضج 1800 ⇒ تقدّم ≈ 0.111 ⇒ مرحلة initial.
    st = crop_twin_state("wheat", _wheat_days(10), taw_mm=100.0, raw_fraction=0.5)
    assert st["phenology"]["gdd_cumulative"] == pytest.approx(200.0)
    assert st["phenology"]["progress"] == pytest.approx(200.0 / 1800.0, rel=1e-3)
    assert st["phenology"]["stage"] == "initial"
    assert st["phenology"]["past_maturity"] is False


def test_past_maturity_flagged():
    # 100 يوم × 20 = 2000 > 1800 ⇒ past_maturity، تقدّم مقصوص عند 1.0، مرحلة late.
    st = crop_twin_state("wheat", _wheat_days(100), taw_mm=100.0, raw_fraction=0.5)
    assert st["phenology"]["past_maturity"] is True
    assert st["phenology"]["progress"] == pytest.approx(1.0)
    assert st["phenology"]["stage"] == "late"
    assert any("النضج" in w for w in st["warnings_ar"])


def test_water_block_mirrors_root_zone_balance():
    days = _wheat_days(6)  # etc=10/يوم ⇒ Dr نهائيّ 60، RAW 50.
    st = crop_twin_state("wheat", days, taw_mm=100.0, raw_fraction=0.5)
    rz = root_zone_balance(
        [DayInput(et0_mm=20.0, kc=0.5) for _ in range(6)], taw_mm=100.0, raw_fraction=0.5
    )
    assert st["water"]["depletion_mm"] == pytest.approx(rz.final_depletion_mm)
    assert st["water"]["raw_mm"] == pytest.approx(rz.raw_mm)
    assert st["water"]["needs_irrigation"] is True
    assert st["water"]["depletion_pct"] == pytest.approx(60.0)
    assert st["water"]["trigger_days"] == rz.trigger_days


def test_nutrient_block_mirrors_uptake_at_progress():
    days = _wheat_days(10)
    st = crop_twin_state("wheat", days, taw_mm=100.0, raw_fraction=0.5, target_uptake_kg_ha=120.0)
    progress = st["phenology"]["progress"]
    nut = nutrient_uptake("wheat", progress, 120.0)
    assert st["nutrient"]["uptake_to_date_kg_ha"] == pytest.approx(nut["uptake_to_date_kg_ha"])
    assert st["nutrient"]["target_uptake_kg_ha"] == pytest.approx(120.0)


def test_unknown_crop_flagged_and_generic_params():
    st = crop_twin_state("zucchini_x", _wheat_days(5), taw_mm=100.0, raw_fraction=0.5)
    assert st["crop_known"] is False
    assert any("غير مُعرّف" in w for w in st["warnings_ar"])
    # معاملات عامّة (t_base=5) ⇒ GDD/يوم = mean(10,30)/.. = 20-5 = 15 ⇒ 5 أيّام = 75.
    assert st["phenology"]["gdd_cumulative"] == pytest.approx(75.0)


def test_calibrated_false():
    st = crop_twin_state("wheat", _wheat_days(3), taw_mm=100.0, raw_fraction=0.5)
    assert st["calibrated"] is False


def test_empty_days_respects_initial_depletion():
    st = crop_twin_state("wheat", [], taw_mm=100.0, raw_fraction=0.5, initial_depletion_mm=30.0)
    assert st["phenology"]["gdd_cumulative"] == 0.0
    assert st["phenology"]["progress"] == 0.0
    assert st["phenology"]["stage"] == "initial"
    assert st["water"]["depletion_mm"] == pytest.approx(30.0)
    assert st["water"]["needs_irrigation"] is False  # 30 < RAW 50


def test_auto_irrigate_reflected_in_state():
    days = _wheat_days(6)
    st = crop_twin_state("wheat", days, taw_mm=100.0, raw_fraction=0.5, auto_irrigate=True)
    # يُملأ Dr يوم 4 ⇒ يوم 5 من 0 +10 ⇒ Dr نهائيّ 10، لا حاجة.
    assert st["water"]["depletion_mm"] == pytest.approx(10.0)
    assert st["water"]["needs_irrigation"] is False
    assert st["water"]["trigger_days"] == [4]
