"""اختبارات سياسة مراحل GDD (api.gdd_tracker.stage_result_from_cumulative) — دالّة نقيّة.

WS-C.1c Zero-Legacy: نواة GDD اليوميّة (daily_gdd) وحلقة التراكم (track_gdd) أُزيلتا —
مِلك محرّك الطقس (services/weather-service/gdd.py، وتُختبَر هناك). يبقى هنا اختبار **سياسة
الموسم** فقط: تعيين المرحلة الحاليّة/التالية والـGDD المتبقّي من تراكميّ (مُعطى) + عتبات
``GDD_CROP_PARAMS``، لوحة ``stage_progress``، حالة النضج، ``to_dict``، ومحصول مجهول.
"""

import pytest
from api.gdd_tracker import (
    GDD_CROP_PARAMS,
    GDDResult,
    stage_result_from_cumulative,
)

pytestmark = pytest.mark.unit


# ─── تعيين المرحلة من التراكميّ ───────────────────────────────────


def test_zero_cumulative_starts_at_planting():
    r = stage_result_from_cumulative("wheat", 0.0, 0)
    assert r.cumulative_gdd == 0.0
    assert r.days_counted == 0
    assert r.current_stage == "planting"
    # المرحلة التالية = أوّل مرحلة (emergence) والـGDD المتبقّي = عتبتها.
    assert r.next_stage == "emergence"
    assert r.gdd_to_next_stage == 120.0
    assert r.t_base == 0.0


def test_reaches_first_stage():
    # 150 ≥ emergence(120) لكن < tillering(400).
    r = stage_result_from_cumulative("wheat", 150.0, 10)
    assert r.current_stage == "emergence"
    assert r.next_stage == "tillering"
    assert r.gdd_to_next_stage == 400 - 150  # = 250
    assert r.days_counted == 10


def test_before_first_threshold_stays_planting():
    r = stage_result_from_cumulative("wheat", 75.0, 5)
    assert r.current_stage == "planting"
    assert r.next_stage == "emergence"
    assert r.gdd_to_next_stage == 120 - 75  # = 45


def test_threshold_inclusive_boundary():
    # عتبة شاملة: cumulative == threshold ⇒ المرحلة بُلِغت.
    r = stage_result_from_cumulative("wheat", 120.0, 8)
    assert r.current_stage == "emergence"
    assert r.gdd_to_next_stage == 400 - 120  # = 280


def test_maturity_reached_has_no_next_stage():
    r = stage_result_from_cumulative("wheat", 5000.0, 200)
    assert r.current_stage == "maturity"
    assert r.next_stage is None
    assert r.gdd_to_next_stage is None
    assert "النضج" in r.notes_ar


def test_intermediate_stage_tillering():
    r = stage_result_from_cumulative("wheat", 450.0, 30)
    assert r.current_stage == "tillering"
    assert r.next_stage == "heading"
    assert r.gdd_to_next_stage == 900 - 450  # = 450


# ─── stage_progress ──────────────────────────────────────────────


def test_stage_progress_reflects_reached_flags():
    r = stage_result_from_cumulative("wheat", 150.0, 10)
    prog = {p["stage"]: p for p in r.stage_progress}
    assert prog["emergence"]["reached"] is True
    assert prog["emergence"]["gdd_threshold"] == 120
    assert prog["tillering"]["reached"] is False
    assert [p["stage"] for p in r.stage_progress] == [
        name for name, _ in GDD_CROP_PARAMS["wheat"]["stages"]
    ]


# ─── المحاصيل المختلفة ومعاملاتها ────────────────────────────────


def test_sorghum_uses_its_base_temp():
    # sorghum t_base=10؛ التراكميّ 100 = emergence(100).
    r = stage_result_from_cumulative("sorghum", 100.0, 10)
    assert r.t_base == 10.0
    assert r.current_stage == "emergence"


def test_each_crop_has_five_named_stages():
    for crop, params in GDD_CROP_PARAMS.items():
        r = stage_result_from_cumulative(crop, 0.0, 0)
        assert r.crop == crop
        assert len(r.stage_progress) == len(params["stages"]) == 5


# ─── محصول غير معروف ─────────────────────────────────────────────


def test_unknown_crop_raises_value_error():
    with pytest.raises(ValueError) as e:
        stage_result_from_cumulative("banana", 100.0, 5)
    assert "banana" in str(e.value)
    assert "wheat" in str(e.value)


# ─── to_dict والتقريب ────────────────────────────────────────────


def test_to_dict_rounds_and_preserves_fields():
    r = stage_result_from_cumulative("wheat", 150.0, 10)
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
    d = stage_result_from_cumulative("wheat", 5000.0, 200).to_dict()
    assert d["next_stage"] is None
    assert d["gdd_to_next_stage"] is None


def test_to_dict_rounds_fractional_gdd():
    # التراكميّ 15.125 يُقرّب إلى 15.1 في to_dict.
    r = stage_result_from_cumulative("wheat", 15.125, 1)
    assert r.cumulative_gdd == 15.125
    assert r.to_dict()["cumulative_gdd"] == 15.1


def test_returns_gddresult_instance():
    r = stage_result_from_cumulative("wheat", 0.0, 0)
    assert isinstance(r, GDDResult)
