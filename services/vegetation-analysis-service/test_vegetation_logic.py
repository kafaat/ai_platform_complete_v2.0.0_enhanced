"""RIV vegetation interpretation tests: no spectral computation lives here."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from main import _current_ndvi_payload, _health_classification, _recommendations_ar
from vegetation_runtime import _derive_water_stress_from_observed


def test_water_stress_uses_observed_ndmi_msi():
    assert _derive_water_stress_from_observed({"ndmi": 0.4, "msi": 0.4}) == 0.0
    assert _derive_water_stress_from_observed({"ndmi": -0.4, "msi": 2.0}) == 1.0


def test_water_stress_missing_inputs_is_neutral_not_invented_extreme():
    assert _derive_water_stress_from_observed({}) == 0.5


def test_health_thresholds_ordered():
    scores = [
        _health_classification(0.75, 0.2)["score"],
        _health_classification(0.6, 0.4)["score"],
        _health_classification(0.45, 0.6)["score"],
        _health_classification(0.25, 0.5)["score"],
        _health_classification(0.1, 0.5)["score"],
    ]
    assert scores == sorted(scores, reverse=True)


def test_recommendations_are_hypotheses_and_delegate_decision():
    recs = _recommendations_ar({"ndvi": 0.6, "water_stress": 0.7, "ndmi": -0.1}, {}, "wheat")
    joined = " ".join(recs)
    assert "فرضيّة" in joined and "خدمة القرار" in joined


def test_current_ndvi_payload_preserves_truth_flags():
    field = {"name": "حقل", "crop": "wheat"}
    analysis = {
        "indices": {"ndvi": {"value": 0.71}},
        "health": {"status": "good"},
        "acquisition_date": "2026-07-01",
        "data_source": "raster-service",
        "real_data": True,
        "provider_reachable": True,
    }
    out = _current_ndvi_payload("f", field, analysis)
    assert out["ndvi"]["current"] == 0.71 and out["real_data"] is True


def test_no_spectral_formula_exports_from_main():
    import main

    assert not hasattr(main, "_compute_indices")
    assert not hasattr(main, "_realistic_bands")
