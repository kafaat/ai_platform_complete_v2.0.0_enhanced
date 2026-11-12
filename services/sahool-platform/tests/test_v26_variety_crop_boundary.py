"""v26 workstream 02: the active season's crop and variety drive field_state; a variety card
of another crop is excluded and the conflict reaches the decision as a review requirement."""

import pytest
from api.field_state_projection import (
    _compose_agronomic,
    escalate_context_conflicts,
    season_crop_context,
)
from core.agronomic_state_engine import CropContext, SignalInput, compose_field_state
from core.season_phenology import resolve_crop_id

VARIETY_TRUTHS = ("variety_id", "variety_drought_tolerance", "maturity_class")


@pytest.mark.unit
@pytest.mark.parametrize("foreign", ["sorghum_local_qairaa", "peanut_karz"])
def test_foreign_variety_is_never_applied_to_wheat(foreign):
    state = compose_field_state(
        "f1",
        [SignalInput(source="soil_ec", value=8.0)],
        crop_context=CropContext(crop_id="wheat", variety_id=foreign, days_after_planting=30),
    )
    for key in VARIETY_TRUTHS + ("salinity_threshold_shift",):
        assert key not in state.operational_truths, key
    mismatch = [c for c in state.contradictions if isinstance(c, dict)]
    assert mismatch and mismatch[0]["type"] == "variety_crop_mismatch"
    assert mismatch[0]["parent_crop_id"] == foreign.split("_")[0]
    assert mismatch[0]["resolution"] == "excluded_from_decision"


@pytest.mark.unit
def test_matching_variety_still_applies():
    state = compose_field_state(
        "f1",
        [SignalInput(source="soil_ec", value=2.0)],
        crop_context=CropContext(crop_id="wheat", variety_id="wheat_aziz", days_after_planting=30),
    )
    assert state.operational_truths["variety_id"] == "wheat_aziz"
    assert state.operational_truths["variety_drought_tolerance"] == "medium"
    assert not [c for c in state.contradictions if isinstance(c, dict)]


@pytest.mark.unit
def test_active_season_crop_overrides_field_crop_and_declares_the_conflict():
    crop, variety, sowing, conflicts = season_crop_context(
        "sorghum",
        {"crops": '["قمح"]', "cultivar": " peanut_karz ", "sowing_date": None},
        resolve_crop_id,
    )
    assert (crop, variety, sowing) == ("wheat", "peanut_karz", None)
    assert conflicts == [
        {
            "type": "field_season_crop_mismatch",
            "field_crop": "sorghum",
            "season_crop": "wheat",
            "requires_review": True,
        }
    ]
    mixed = season_crop_context(
        "wheat", {"crops": ["wheat", "barley"], "cultivar": None}, resolve_crop_id
    )
    assert mixed[0] is None and mixed[3][0]["type"] == "mixed_crop_not_modeled"
    assert season_crop_context("wheat", None, resolve_crop_id) == ("wheat", None, None, [])


@pytest.mark.unit
def test_wrong_variety_reaches_the_decision_as_review_and_without_its_traits():
    """The projection path recompute_field_state runs: compose → escalate → execution_mode."""
    agronomic = _compose_agronomic(
        "f1", "t1", 0.7, 2.0, crop_id="wheat", days_after_planting=40, variety_id="sorghum_ghurbah"
    )
    assert agronomic is not None
    for key in VARIETY_TRUTHS:
        assert key not in agronomic["operational_truths"], key
    state = {"execution_mode": "auto", "validity": "valid", "agronomic": agronomic}
    escalate_context_conflicts(state)
    assert state["execution_mode"] == "human_review"
    assert state["validity"] == "degraded"
    assert "variety_crop_mismatch" in state["reasons_ar"][-1]


@pytest.mark.unit
def test_escalation_only_raises_and_ignores_clean_states():
    clean = {"execution_mode": "auto", "validity": "valid", "agronomic": {"contradictions": []}}
    escalate_context_conflicts(clean)
    assert clean["execution_mode"] == "auto" and "reasons_ar" not in clean
    blocked = {
        "execution_mode": "blocked",
        "validity": "invalid",
        "context_conflicts": [{"type": "mixed_crop_not_modeled", "requires_review": True}],
    }
    escalate_context_conflicts(blocked)
    assert blocked["execution_mode"] == "blocked" and blocked["validity"] == "invalid"
