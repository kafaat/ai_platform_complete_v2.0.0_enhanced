from datetime import UTC, datetime, timedelta, timezone

from p4_governance import build_learning, evaluate_action

from shared.contracts.soil.p4 import SoilExecutionRecord, SoilOutcomeRecord


def profile(level="lab_verified", conflicts=None):
    now = datetime.now(UTC).isoformat()
    names = [
        "ph",
        "ec",
        "organic_matter",
        "nitrogen",
        "phosphorus",
        "potassium",
        "field_capacity",
        "wilting_point",
        "infiltration",
        "esp",
        "cec",
        "ksat",
        "water_table_depth",
    ]
    return {
        "evidence_level": level,
        "profile_hash": "abc",
        "properties": {n: {"value": 1, "observed_at": now} for n in names},
        "conflicts": conflicts or [],
        "quality_gate": {"passed": True},
    }


def test_fertilizer_requires_lab_and_properties():
    assert evaluate_action(profile(), "fertilizer_rate").allowed
    p = profile("field_observed")
    assert not evaluate_action(p, "fertilizer_rate").allowed


def test_leaching_requires_water_drainage_and_no_conflict():
    p = profile()
    r = evaluate_action(
        p, "leaching_requirement", water_profile_approved=True, drainage_verified=True
    )
    assert r.allowed
    p["conflicts"] = ["ec_conflict"]
    assert not evaluate_action(
        p, "leaching_requirement", water_profile_approved=True, drainage_verified=True
    ).allowed


def test_stale_evidence_blocked():
    p = profile()
    p["properties"]["ec"]["observed_at"] = (datetime.now(UTC) - timedelta(days=500)).isoformat()
    assert "evidence_stale" in evaluate_action(p, "fertilizer_rate").reasons


def test_learning_requires_verification():
    e = SoilExecutionRecord(
        tenant_id="t",
        field_id="f",
        decision_id="d",
        action_type="gypsum_rate",
        profile_hash="h",
        approved_by=["u"],
    )
    o = SoilOutcomeRecord(
        tenant_id="t", field_id="f", execution_id=e.execution_id, effectiveness_score=0.8
    )
    learning = build_learning(o, e, profile())
    assert (
        not learning.eligible_for_training and "verification_missing" in learning.exclusion_reasons
    )
