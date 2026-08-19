import pytest
from api.unified_decision import (
    canonical_agronomic_context,
    irrigation_closed_loop_advisory,
    nutrient_salinity_ledger,
    precision_yield_response,
    spectral_action_candidate,
    unified_decision,
)

# منطقٌ صرف بلا قاعدة ولا خدمة. وظيفة CI تُشغّل `pytest tests` بلا `-m` فالملفّ
# يعمل معلَّماً أو لا، لكنّ العلامة تُخرِجه من مجموعة «ما يسقط صامتاً لو أُضيف
# `-m unit` لاحقاً» — وهو صنف العطل الذي يحرسه `test_marker_coverage_guard` في
# `tests_v9`، ولا يبلغ هذا الدليل.
pytestmark = pytest.mark.unit


def _field_state():
    return {
        "field_id": "f-1",
        "season_id": "s-1",
        "as_of_time": "2026-08-19T00:00:00Z",
        "state_digest": "a" * 64,
        "availability": {"weather": True, "water": True, "soil": True, "spectral": True},
        "evidence_digests": {"weather": "b" * 64},
        "eligibility": {"propose": {"allowed": True, "reasons": []}},
        "soil": {"schema_version": "canonical_soil_state.v1", "soil_ece": 3.2},
        "spectral": {
            "schema_version": "canonical_spectral_state.v1",
            "quality_status": "validated",
            "stress_class": "critical",
        },
        "water": {"schema_version": "canonical_water_state.v1", "quality_status": "verified"},
    }


def test_agri_next_1_irrigation_is_capacity_and_cost_constrained_without_execution():
    plan = {"days": [{"day_index": 0, "irrigation_mm": 12.0}], "budget_exhausted": False}
    out = irrigation_closed_loop_advisory(
        field_state=_field_state(),
        irrigation_plan=plan,
        capacity={
            "max_application_mm": 8.0,
            "remaining_volume_m3": 300,
            "target_area_ha": 5,
            "energy_kwh_per_m3": 0.4,
        },
        economics={"water_price_per_m3": 0.1, "energy_price_per_kwh": 0.2},
    )
    assert out["capacity_constrained_mm"] == 6.0
    assert out["estimated_event_m3"] == 300.0
    assert out["estimated_water_energy_cost"] == 54.0
    assert out["direct_execution_permitted"] is False
    assert "remaining_volume_limited" in out["constraint_reasons"]


def test_agri_next_2_context_is_point_in_time_and_owner_digest_bound():
    out = canonical_agronomic_context(
        field_state=_field_state(), crop_twin={"crop": "wheat", "phenology": {"stage": "mid"}}
    )
    assert out["context_complete"] is True
    assert out["field_state_digest"] == "a" * 64
    assert out["phenology"]["stage"] == "mid"
    assert len(out["context_digest"]) == 64


def test_agri_next_3_nutrient_salinity_ledger_never_invents_rate():
    out = nutrient_salinity_ledger(
        soil_state={"soil_ece": 4.1},
        irrigation_water={"water_ec": 1.8},
        nutrient_events=[{"nutrient": "n", "kg_ha": 40}, {"nutrient": "n", "kg_ha": 20}],
        crop_demand_kg_ha={"n": 100},
    )
    assert out["balances"]["n"]["remaining_kg_ha"] == 40.0
    assert out["salinity_status"] == "measured_requires_crop_tolerance"
    assert out["fertilizer_rate_authoritative"] is False


def test_agri_next_4_spectral_stress_nominates_candidate_never_executes():
    ctx = canonical_agronomic_context(field_state=_field_state(), crop_twin={"crop": "wheat"})
    out = spectral_action_candidate(
        spectral_state=_field_state()["spectral"], agronomic_context=ctx
    )
    assert out["candidate_status"] == "pending_decision"
    assert out["submit_to_decision"] is True
    assert out["direct_action_permitted"] is False


def test_agri_next_4_degraded_spectral_is_fail_closed():
    ctx = canonical_agronomic_context(field_state=_field_state(), crop_twin={"crop": "wheat"})
    out = spectral_action_candidate(
        spectral_state={"quality_status": "degraded", "stress_class": "critical"},
        agronomic_context=ctx,
    )
    assert out["candidate_status"] == "evidence_required"
    assert out["submit_to_decision"] is False


def test_agri_next_5_response_is_observational_not_causal_or_promotional():
    out = precision_yield_response(
        planned_rates=[{"zone_id": "z1", "rate": 100}],
        as_applied=[{"zone_id": "z1", "rate": 90}],
        yield_samples=[{"zone_id": "z1", "yield_kg_ha": 5000}],
    )
    assert out["zones"][0]["application_variance_pct"] == -10.0
    assert out["quality_status"] == "observed_response"
    assert out["causal_claim_permitted"] is False
    assert out["automatic_model_promotion_eligible"] is False


def test_unified_decision_exposes_all_five_closures_without_changing_existing_keys():
    out = unified_decision(
        crop_twin={
            "crop": "wheat",
            "phenology": {},
            "water": {},
            "nutrient": {},
            "warnings_ar": [],
        },
        irrigation_plan={"policy": "water_saving", "days": [], "stress_days": [], "notes_ar": []},
        quality={"confidence": 0.8, "data_quality": "good"},
        field_state=_field_state(),
        irrigation_capacity={"target_area_ha": 1.0},
        irrigation_water={"water_ec": 1.0},
        nutrient_events=[],
        crop_demand_kg_ha={},
    )
    assert out["crop"] == "wheat"
    for key in (
        "agronomic_context",
        "irrigation_closed_loop",
        "nutrient_salinity_ledger",
        "spectral_action_candidate",
        "precision_yield_response",
    ):
        assert key in out


# ── لا رفضَ بلا سببٍ مذكور ────────────────────────────────────────────────────
# العطل الذي تمنعه هذه الحالات: `proposal_allowed=False` مع `reason_codes=[]`،
# فيقرأ المستهلك منعاً بلا ما يُفسّره ويُخمّن سببه. وقع فعلاً حين يحضر
# `field_state` وتكون `eligibility.propose.allowed` كاذبةً أو غائبة بلا `reasons`
# ولا قيدَ سعةٍ أو ميزانيّةٍ يُضيف سبباً.

_PLAN = {"days": [{"day_index": 1, "irrigation_mm": 8.0}]}
_CAP = {"max_application_mm": 20.0, "target_area_ha": 2.0}


@pytest.mark.parametrize("propose", [{"allowed": False}, {}, {"allowed": False, "reasons": []}])
def test_irrigation_refusal_always_states_a_reason(propose):
    out = irrigation_closed_loop_advisory(
        field_state={"eligibility": {"propose": propose}},
        irrigation_plan=_PLAN,
        capacity=_CAP,
    )
    assert out["proposal_allowed"] is False
    assert out["reason_codes"] == ["field_eligibility_not_proposable"]


def test_irrigation_default_reason_never_masks_an_explicit_one():
    """السبب الافتراضيّ يسدّ الصمت فقط — ولا يُزيح سبباً مقيساً ولا مُصرَّحاً."""
    explicit = irrigation_closed_loop_advisory(
        field_state={"eligibility": {"propose": {"allowed": False, "reasons": ["agronomy_hold"]}}},
        irrigation_plan=_PLAN,
        capacity=_CAP,
    )
    assert explicit["reason_codes"] == ["agronomy_hold"]

    measured = irrigation_closed_loop_advisory(
        field_state={"eligibility": {"propose": {"allowed": True}}},
        irrigation_plan=_PLAN,
        capacity={"max_application_mm": 0.0, "target_area_ha": 2.0},
    )
    assert measured["proposal_allowed"] is False
    assert measured["reason_codes"] == ["delivery_capacity_zero"]

    missing = irrigation_closed_loop_advisory(
        field_state=None, irrigation_plan=_PLAN, capacity=_CAP
    )
    assert missing["reason_codes"] == ["field_state_missing"]


def test_irrigation_permission_is_not_given_a_manufactured_reason():
    """والسماح يبقى سماحاً: لا يُقحَم سببٌ في مسارٍ لم يُمنَع."""
    out = irrigation_closed_loop_advisory(
        field_state={"eligibility": {"propose": {"allowed": True}}},
        irrigation_plan=_PLAN,
        capacity=_CAP,
    )
    assert out["proposal_allowed"] is True
    assert out["reason_codes"] == []
    assert out["direct_execution_permitted"] is False
