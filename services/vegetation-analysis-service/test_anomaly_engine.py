from datetime import UTC, datetime
from decimal import Decimal

from anomaly_engine import detect_signals


def _comparison(pct="-22", deviation="-0.12", confidence="0.75", sample=4):
    return {
        "baseline_run_ref": "urn:sahool:processing-run:run_demo",
        "baseline_type": "same_phenological_stage",
        "primary_observation_ref": "urn:sahool:observation:obs_current",
        "deviation": deviation,
        "deviation_percent": pct,
        "expected_confidence": confidence,
        "sample_size": sample,
    }


def test_detects_signal_not_diagnosis():
    result = detect_signals(
        field_id="fld_demo",
        indicator="ndvi",
        comparisons=[_comparison()],
        now=datetime(2026, 7, 15, tzinfo=UTC),
    )
    assert len(result) == 1
    signal = result[0]
    assert signal.signal_type == "ndvi_decline"
    assert signal.severity == "high"
    assert signal.verification_requirement == "required"
    assert "water_stress" not in str(signal.to_dict())


def test_ignores_small_deviation():
    assert (
        detect_signals(
            field_id="fld_demo",
            indicator="ndvi",
            comparisons=[_comparison(pct="-4")],
            min_deviation_percent=Decimal("7"),
        )
        == []
    )


def test_deduplicates_multiple_baselines_to_strongest():
    result = detect_signals(
        field_id="fld_demo",
        indicator="ndvi",
        comparisons=[_comparison(pct="-12"), _comparison(pct="-31", deviation="-0.20")],
    )
    assert len(result) == 1
    assert result[0].severity == "critical"
