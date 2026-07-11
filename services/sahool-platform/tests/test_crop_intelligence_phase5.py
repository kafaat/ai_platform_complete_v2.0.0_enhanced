from datetime import UTC, datetime

import pytest
from core.crop_intelligence import CropIntelligenceInput, build_crop_intelligence_state
from core.crop_intelligence.stress_memory import build_stress_memory


def test_stress_memory_is_time_aware_and_persistence_ready():
    out = build_stress_memory(
        [
            {
                "type": "water",
                "severity": 1.0,
                "observed_at": "2026-07-08T00:00:00Z",
                "evidence_id": "e1",
            },
            {
                "type": "water",
                "severity": 1.0,
                "observed_at": "2026-07-09T00:00:00Z",
                "evidence_id": "e1b",
            },
            {
                "type": "water",
                "severity": 0.2,
                "observed_at": "2026-07-10T00:00:00Z",
                "evidence_id": "e2",
            },
        ],
        as_of="2026-07-11T00:00:00Z",
        half_life_days=7,
    )
    assert out["schema"] == "crop_stress_memory.v2"
    assert out["status"] == "available"
    assert out["recovery_state"] == "recovering"
    assert out["latest_observed_at"] == "2026-07-10T00:00:00Z"
    assert out["persistence"]["raw_history_required_for_recompute"] is True
    assert out["evidence_ids"] == ["e1", "e1b", "e2"]


def test_stale_observations_are_excluded_not_fabricated():
    out = build_stress_memory(
        [{"type": "heat", "severity": 0.8, "observed_at": "2026-01-01T00:00:00Z"}],
        as_of="2026-07-11T00:00:00Z",
        max_age_days=30,
    )
    assert out["status"] == "unavailable"
    assert out["overall_burden"] is None
    assert out["stale_count"] == 1
    assert "all_stress_observations_stale" in out["limitations"]


def test_future_and_non_finite_observations_are_rejected():
    out = build_stress_memory(
        [
            {"type": "water", "severity": float("nan"), "observed_at": "2026-07-10T00:00:00Z"},
            {"type": "heat", "severity": 0.4, "observed_at": "2026-07-12T00:00:00Z"},
        ],
        as_of="2026-07-11T00:00:00Z",
    )
    assert out["status"] == "invalid"
    assert out["rejected_count"] == 2


def test_invalid_as_of_fails_explicitly():
    with pytest.raises(ValueError):
        build_stress_memory([], as_of="not-a-time")


def test_crop_state_v5_embeds_versioned_stress_memory():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(
            crop="wheat",
            gdd_cumulative=500,
            gdd_to_maturity=1800,
            stress_history=[
                {"type": "water", "severity": 0.6, "observed_at": "2026-07-10T00:00:00Z"}
            ],
            stress_memory_as_of="2026-07-11T00:00:00Z",
            stress_memory_policy={"half_life_days": 5, "max_age_days": 20},
        )
    )
    assert out["engine_version"] == "crop-intelligence/5.0.0"
    assert out["stress_memory"]["schema"] == "crop_stress_memory.v2"
    assert out["stress_memory"]["half_life_days"] == 5.0


def test_naive_datetime_is_normalized_to_utc():
    out = build_stress_memory(
        [{"type": "cold", "severity": 0.2, "observed_at": datetime(2026, 7, 10)}],
        as_of=datetime(2026, 7, 11, tzinfo=UTC),
    )
    assert out["latest_observed_at"].endswith("Z")
