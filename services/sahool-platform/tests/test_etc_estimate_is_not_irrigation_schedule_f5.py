"""F5 — an ETc figure must not be presented as scheduled irrigation.

``irrigation_advice`` computes ``ETc − effective rain`` (ET0 × Kc, minus recent rain). FAO-56
irrigation scheduling (Ch. 8, eq. 85) needs a root-zone water balance: the depletion Dr
against TAW and the allowable fraction p. This function reads none of the three, yet the
hub titled its figure "ريّ مُوصى به: X مم — خلال ٢٤ ساعة" and the payload named nothing.

After the fix the payload names the figure a consumption estimate, says no root-zone
balance backs it, and lists the inputs a schedule needs; the hub title follows that name.
No threshold, coefficient or depth is introduced here. Pure logic, no network or database.
"""

from datetime import date

import pytest
from api.irrigation_recommendation_policy import recommend_irrigation
from api.recommendations_hub import RecommendationContext, _irrigation_rec
from api.weather_advice import (
    QUANTITY_KIND_ETC_ESTIMATE,
    ROOT_ZONE_SCHEDULE_MISSING_INPUTS,
    irrigation_advice,
)

pytestmark = pytest.mark.unit

_MISSING = ["root_zone_depletion_mm", "total_available_water_mm", "depletion_fraction_p"]


def _ctx(**over) -> RecommendationContext:
    base = dict(
        field_id="f1",
        crop="wheat",
        stage="mid",
        et0_mm=6.0,
        rain_recent_mm=0.0,
        forecast_rain_mm=0.0,
        today=date(2026, 11, 8),
    )
    base.update(over)
    return RecommendationContext(**base)


def test_codes_are_stable():
    assert QUANTITY_KIND_ETC_ESTIMATE == "etc_consumption_estimate"
    assert list(ROOT_ZONE_SCHEDULE_MISSING_INPUTS) == _MISSING


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(et0_mm=6.0, crop="wheat", stage="mid"),  # moderate ⇒ «خلال ٢٤ ساعة»
        dict(et0_mm=9.0, crop="wheat", stage="mid"),  # high
        dict(et0_mm=2.0, crop="wheat", stage="initial"),  # low
        dict(et0_mm=6.0, crop="wheat", stage="mid", rain_recent_mm=40.0),  # none
        dict(et0_mm=6.0, crop="dragonfruit", stage="mid"),  # unknown crop ⇒ range
        # A point soil-moisture reading moves urgency only: it is not a root-zone balance.
        dict(
            et0_mm=6.0,
            crop="wheat",
            stage="mid",
            soil_moisture_pct=20.0,
            soil_moisture_unit_kind="available_pct",
        ),
    ],
)
def test_advice_names_its_figure_a_consumption_estimate_and_lists_missing_inputs(kwargs):
    advice = irrigation_advice(**kwargs)
    assert advice["quantity_kind"] == "etc_consumption_estimate", advice
    assert advice["root_zone_balance_backed"] is False, advice
    assert advice["irrigation_schedule_missing_inputs"] == _MISSING, advice


def test_claim_moderate_etc_is_not_titled_recommended_irrigation_within_24h():
    """The audit's witness: ET0 6.0 × Kc(wheat, mid) with no rain and no soil data."""
    advice = irrigation_advice(et0_mm=6.0, crop="wheat", stage="mid")
    assert advice["urgency"] == "moderate" and advice["timing_ar"] == "خلال ٢٤ ساعة"
    rec = _irrigation_rec(_ctx())
    assert rec is not None
    assert "ريّ مُوصى به" not in rec.title_ar, rec.title_ar
    assert "خلال ٢٤ ساعة" not in rec.title_ar, rec.title_ar
    assert "تقدير استهلاك" in rec.title_ar, rec.title_ar
    assert f"{advice['recommended_mm']:.1f}" in rec.title_ar, "the figure itself is kept"
    for code in _MISSING:
        assert code in rec.detail_ar, rec.detail_ar
    assert rec.priority == "medium", "urgency still maps to priority; only the name changed"


def test_missing_inputs_list_is_a_copy_callers_cannot_mutate():
    first = irrigation_advice(et0_mm=6.0, crop="wheat", stage="mid")
    first["irrigation_schedule_missing_inputs"].clear()
    second = irrigation_advice(et0_mm=6.0, crop="wheat", stage="mid")
    assert second["irrigation_schedule_missing_inputs"] == _MISSING


def test_numbers_urgency_and_limitations_are_unchanged():
    """Naming only: no quantity, urgency, timing or limitation moves."""
    advice = irrigation_advice(et0_mm=6.0, crop="wheat", stage="mid")
    assert advice["recommended_mm"] == 6.9
    assert advice["urgency"] == "moderate"
    assert advice["limitations"] == []
    assert advice["advisory_range_mm"] is None


def test_no_need_and_unknown_crop_titles_keep_their_wording():
    wet = _irrigation_rec(_ctx(rain_recent_mm=40.0))
    assert wet is not None and wet.title_ar.startswith("لا حاجة للريّ الآن"), wet.title_ar
    unknown = _irrigation_rec(_ctx(crop="dragonfruit"))
    assert unknown is not None and "تقديريّ" in unknown.title_ar, unknown.title_ar
    assert "ريّ مُوصى به" not in unknown.title_ar


def test_root_zone_policy_output_does_not_inherit_the_estimate_marker():
    """``recommend_irrigation`` owns the depletion trigger: it declares its own state."""
    backed = recommend_irrigation(
        et0_mm=6.0,
        crop="wheat",
        stage="mid",
        rain_recent_mm=0.0,
        forecast_rain_mm=0.0,
        depletion_mm=30.0,
        taw_mm=100.0,
    )
    assert backed["trigger_reason"] != "no_depletion_data", backed["trigger_reason"]
    unbacked = recommend_irrigation(
        et0_mm=6.0, crop="wheat", stage="mid", rain_recent_mm=0.0, forecast_rain_mm=0.0
    )
    assert unbacked["trigger_reason"] == "no_depletion_data"
    for out in (backed, unbacked):
        assert "quantity_kind" not in out and "root_zone_balance_backed" not in out
        assert not [x for x in out["limitations"] if "etc_consumption" in x], out["limitations"]
