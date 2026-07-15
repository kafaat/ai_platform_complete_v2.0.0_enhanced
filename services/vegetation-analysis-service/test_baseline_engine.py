from baseline_engine import build_baselines


def _entry(ref, date, value, stage=None):
    return {
        "observation_ref": ref,
        "acquired_at": date,
        "indicator": {"code": "ndvi"},
        "summary": {"kind": "continuous", "mean": value},
        "observation_quality": {"gate_status": "passed"},
        "stage": stage,
    }


def test_previous_robust_and_stage_baselines():
    entries = [
        _entry("urn:sahool:observation:obs_a", "2026-06-01T00:00:00Z", "0.40"),
        _entry("urn:sahool:observation:obs_b", "2026-06-10T00:00:00Z", "0.50"),
        _entry("urn:sahool:observation:obs_c", "2026-06-20T00:00:00Z", "0.45"),
        _entry("urn:sahool:observation:obs_d", "2026-07-01T00:00:00Z", "0.60"),
    ]
    stages = {
        "urn:sahool:observation:obs_a": "vegetative",
        "urn:sahool:observation:obs_c": "vegetative",
    }
    result = build_baselines(
        field_id="fld_demo",
        indicator="ndvi",
        entries=entries,
        stage_by_observation=stages,
        current_stage="vegetative",
    )
    assert [item.baseline_type for item in result] == [
        "previous_valid",
        "historical_robust_median",
        "same_phenological_stage",
    ]
    assert str(result[0].expected_value) == "0.45"
    assert result[2].sample_size == 2


def test_baseline_requires_history():
    assert (
        build_baselines(
            field_id="fld_demo",
            indicator="ndvi",
            entries=[_entry("urn:sahool:observation:obs_a", "2026-07-01T00:00:00Z", "0.60")],
        )
        == []
    )
