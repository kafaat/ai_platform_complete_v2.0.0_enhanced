"""محاكاة الموسم: النافذة لا تُقصّ صامتةً، Kc بعمر المحصول، وربط السجلّ التاريخيّ بالمحصول.

دوالّ نقيّة في ``api.season_simulation`` — بلا قاعدة ولا شبكة:

* النافذة: سقفها دورة المحصول في بطاقته (أو الأرضيّة التاريخيّة ١٦٠ يوماً أيّهما أطول)،
  والقصّ يُعلَن (``truncated`` + الأيّام المطلوبة/المحاكاة + قيد)؛ بلا تاريخ بذار ⇒ رفض.
* Kc: تشغيلٌ في منتصف الموسم يأخذ Kc عمر المحصول الحقيقيّ، لا مرحلةً من توزيعٍ تناسبيّ
  على طول النافذة.
* الربط التلقائيّ: الحقل ويوم البذار لا يكفيان — المحصول نفسه بالمحلِّل القانونيّ على الطرفين.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from api.season_simulation import (
    DayWeather,
    SimContext,
    SimWindowError,
    _seasonal_water_need,
    crop_cycle_window_cap,
    historical_record_crop_matches,
    plan_simulation_window,
    select_auto_link_candidate,
    simulate_season,
)
from core.season_phenology import stage_kc

pytestmark = pytest.mark.unit

_TODAY = date(2026, 11, 8)


# ── النافذة ────────────────────────────────────────────────────────────────────────


def test_missing_sowing_date_is_refused_not_invented():
    with pytest.raises(SimWindowError) as exc:
        plan_simulation_window("wheat", None, None, _TODAY, floor_days=160)
    assert "تاريخ بذار" in exc.value.detail_ar


def test_short_season_is_not_truncated():
    sow = _TODAY - timedelta(days=100)
    end = _TODAY - timedelta(days=10)
    w = plan_simulation_window("wheat", sow, end, _TODAY, floor_days=160)
    assert (w.start, w.end) == (sow, end)
    assert w.truncated is False
    assert w.days_requested == w.days_simulated == 91
    assert w.limitations() == [] and w.warnings_ar() == []


def test_long_window_is_truncated_explicitly():
    sow = _TODAY - timedelta(days=300)
    w = plan_simulation_window("wheat", sow, None, _TODAY, floor_days=160)
    assert w.cap_days == 160  # wheat cycle (120 card / 130 region) < floor
    assert w.truncated is True
    assert w.end == sow + timedelta(days=160)
    assert w.days_requested == 301
    assert w.days_simulated == 161
    assert w.limitations() == ["SIM_WINDOW_TRUNCATED"]
    (warning,) = w.warnings_ar()
    assert "301" in warning and "161" in warning


def test_long_cycle_crop_window_extends_to_its_card_cycle():
    # بطاقة البنّ دورتها 365 يوماً — النافذة لا تُقصّ عند 160.
    cap = crop_cycle_window_cap("coffee", 160)
    assert cap > 160
    sow = _TODAY - timedelta(days=250)
    end = _TODAY - timedelta(days=20)
    w = plan_simulation_window("coffee", sow, end, _TODAY, floor_days=160)
    assert w.truncated is False
    assert w.end == end


def test_cap_never_exceeds_one_year_and_unknown_crop_uses_floor():
    assert crop_cycle_window_cap("Polygonatum", 160) == 160
    assert crop_cycle_window_cap("coffee", 500) == 366


def test_future_or_too_recent_window_is_refused():
    with pytest.raises(SimWindowError):
        plan_simulation_window("wheat", _TODAY - timedelta(days=2), None, _TODAY, floor_days=160)


# ── Kc بعمر المحصول ─────────────────────────────────────────────────────────────────


def test_water_need_uses_card_kc_for_actual_crop_age():
    # نافذة تبدأ يوم 45 من البذار (منتصف الموسم للقمح: 15+25 = 40 ⇒ mid).
    et0 = [1.0] * 30
    need = _seasonal_water_need("wheat", et0, days_since_sowing_start=45)
    expected = sum(stage_kc("wheat", 45 + i) for i in range(30))
    assert need == pytest.approx(expected, abs=0.05)
    # كلّ الأيّام في المرحلة الوسطى (Kc_mid = 1.15) لا «late» من توزيعٍ تناسبيّ.
    assert need == pytest.approx(30 * 1.15)
    proportional = _seasonal_water_need("wheat", et0)
    assert proportional < need


def test_water_need_skips_missing_et0_with_per_day_kc():
    et0 = [1.0, None, 1.0]
    need = _seasonal_water_need("wheat", et0, days_since_sowing_start=0)
    assert need == pytest.approx(2 * 0.30)


def test_unknown_crop_falls_back_to_proportional_generic():
    et0 = [1.0] * 10
    assert _seasonal_water_need("zzz-unknown", et0, 30) == pytest.approx(
        _seasonal_water_need("zzz-unknown", et0)
    )


def test_simulate_season_uses_window_start_offset_for_kc():
    sow = date(2026, 1, 1)
    weather = [DayWeather(t_min_c=10.0, t_max_c=25.0, et0_mm=1.0) for _ in range(20)]
    common = dict(crop="wheat", sowing_date=sow, weather=weather, gdd_daily_override=[10.0] * 20)
    early = simulate_season(SimContext(**common))
    mid = simulate_season(SimContext(**common, window_start=sow + timedelta(days=50)))
    assert early.water_need_mm == pytest.approx(
        sum(stage_kc("wheat", i) for i in range(20)), abs=0.1
    )
    assert mid.water_need_mm == pytest.approx(20 * 1.15, abs=0.1)


# ── ربط السجلّ التاريخيّ ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("season_crop", "ref", "variety", "expected"),
    [
        ("قمح", "wheat", "بحوث 13", True),
        ("wheat", None, "قمح", True),
        ("قمح", "barley", None, False),  # محصول مختلف
        ("خضروات", "wheat", None, False),  # طرف الموسم غير محلول
        ("wheat", None, "بحوث 13", False),  # طرف السجلّ غير محلول
        ("wheat", "wheat", "شعير", False),  # تعارض داخل السجلّ
        (None, "wheat", None, False),
    ],
)
def test_crop_match_uses_canonical_resolver_on_both_sides(season_crop, ref, variety, expected):
    assert historical_record_crop_matches(season_crop, ref, variety) is expected


def _candidate(rid, ref, variety=None):
    return {
        "id": rid,
        "field_id": "field-a",
        "link_crop_registry_ref": ref,
        "link_variety_name": variety,
    }


def test_single_crop_matching_candidate_is_selected_without_helper_columns():
    picked = select_auto_link_candidate(
        [_candidate("r-barley", "barley"), _candidate("r-wheat", "wheat")], "قمح"
    )
    assert picked == {"id": "r-wheat", "field_id": "field-a"}


def test_no_link_when_crops_differ_or_match_is_ambiguous():
    assert select_auto_link_candidate([_candidate("r1", "barley")], "wheat") is None
    assert select_auto_link_candidate([_candidate("r1", None, "بحوث 13")], "wheat") is None
    assert (
        select_auto_link_candidate([_candidate("r1", "wheat"), _candidate("r2", "wheat")], "wheat")
        is None
    )
    assert select_auto_link_candidate([], "wheat") is None
