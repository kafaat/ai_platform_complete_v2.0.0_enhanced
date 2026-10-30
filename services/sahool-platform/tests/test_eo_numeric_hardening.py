"""Unit regressions for EO-04 and explicit, replayable freshness policy."""

import json

import pytest
from api.canonical_water_stress import canonical_water_stress

pytestmark = pytest.mark.unit


def row(**updates):
    return {
        "depletion_mm": 90.0,
        "taw_mm": 100.0,
        "raw_fraction": 0.5,
        "quality_status": "validated",
        "depletion_confidence": 0.9,
        "ndmi": -0.1,
        "msi": 1.2222222222,
        "ndmi_date": "2026-10-27",
        "msi_date": "2026-10-27",
        **updates,
    }


@pytest.mark.parametrize("key", ["depletion_mm", "taw_mm", "raw_fraction"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 10**400, True, "bad"])
def test_bad_physics_never_becomes_normal(key, bad):
    assert canonical_water_stress(row(**{key: bad})) is None


@pytest.mark.parametrize("confidence", [float("inf"), float("nan"), -0.1, 1.5, True, 10**400])
def test_invalid_confidence_never_grants_eligibility(confidence):
    out = canonical_water_stress(row(depletion_confidence=confidence))
    assert out["escalation_eligible"] is False
    assert out["depletion_confidence"] is None
    json.dumps(out, allow_nan=False)


@pytest.mark.parametrize("key", ["ndmi", "msi"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), None, True, 10**400, "invalid"])
def test_invalid_index_is_missing_not_confirmation(key, bad):
    out = canonical_water_stress(row(**{key: bad}))
    assert not out["spectral_confirmation_available"]
    assert not out["escalation_eligible"]
    json.dumps(out, allow_nan=False)


@pytest.mark.parametrize("dr,expected", [(10.0, "normal"), (60.0, "watch"), (90.0, "critical")])
def test_valid_physical_classification_unchanged(dr, expected):
    assert canonical_water_stress(row(depletion_mm=dr))["water_stress_class"] == expected


@pytest.mark.parametrize(
    "changes", [{"depletion_mm": -1}, {"taw_mm": 0}, {"raw_fraction": -0.1}, {"raw_fraction": 1.1}]
)
def test_physical_bounds_are_not_silently_clamped(changes):
    assert canonical_water_stress(row(**changes)) is None


@pytest.mark.parametrize(
    "day,allowed,reason",
    [
        ("2026-10-27", True, "within_explicit_age_policy"),
        ("2026-10-16", True, "within_explicit_age_policy"),
        ("2026-10-15", False, "stale_acquisition"),
        ("2020-01-01", False, "stale_acquisition"),
        ("2030-01-01", False, "future_acquisition"),
        ("2026-10-27garbage", False, "acquisition_date_missing"),
    ],
)
def test_explicit_as_of_policy(day, allowed, reason):
    out = canonical_water_stress(
        row(ndmi_date=day, msi_date=day), as_of="2026-10-28", max_spectral_age_days=12
    )
    assert out["escalation_eligible"] is allowed
    assert out["spectral_freshness"]["reason"] == reason


def test_legacy_caller_does_not_claim_freshness_was_checked():
    out = canonical_water_stress(row(ndmi_date="2020-01-01", msi_date="2020-01-01"))
    assert out["spectral_freshness"]["policy_applied"] is False
    assert out["spectral_freshness"]["verified"] is False


@pytest.mark.parametrize(
    "policy",
    [
        {"as_of": "2026-10-28"},
        {"max_spectral_age_days": 12},
        {"as_of": "bad", "max_spectral_age_days": 12},
        {"as_of": "2026-10-28", "max_spectral_age_days": True},
    ],
)
def test_partial_or_bad_freshness_policy_fails_closed(policy):
    out = canonical_water_stress(row(), **policy)
    assert not out["escalation_eligible"]
    assert out["spectral_freshness"]["reason"] == "invalid_freshness_policy"


def test_explicit_historical_replay_is_supported():
    out = canonical_water_stress(
        row(ndmi_date="2020-01-01", msi_date="2020-01-01"),
        as_of="2020-01-02",
        max_spectral_age_days=12,
    )
    assert out["escalation_eligible"]
    assert out["spectral_freshness"]["verified"]
