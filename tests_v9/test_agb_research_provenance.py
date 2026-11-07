"""Offline contracts for the evidence attached to the AGB research prototype."""

from __future__ import annotations

import builtins
import json
import runpy
from pathlib import Path

import pytest

from random_forest import agb_model

pytestmark = pytest.mark.unit


@pytest.fixture
def features():
    return agb_model.AGBFeatures(
        ndvi=0.72,
        evi=0.61,
        gndvi=0.68,
        savi=0.65,
        vv_backscatter=-12.5,
        vh_backscatter=-18.3,
        area_ha=23.5,
        crop="قمح صلب",
    )


@pytest.fixture(scope="module")
def synthetic_model():
    assert agb_model.HAS_SKLEARN, "RF fitting needs the declared scikit-learn test dependency"
    model = agb_model.SAHOOLAGBModel()
    metrics = model.train_synthetic(n_samples=500)
    return model, metrics


def assert_uncalibrated(result):
    """A plausible point estimate is not evidence of calibrated coverage."""
    assert result["confidence_pct"] is None
    assert result["agb_t_ha_lower"] is None
    assert result["agb_t_ha_upper"] is None
    assert result["model_accuracy"] is None
    assert result["research_only"] is True
    assert result["confidence_calibrated"] is False
    assert result["calibrated_for_this_field"] is False
    assert result["prediction_interval"] == {
        "status": "unavailable",
        "reason": "no_independent_calibration",
        "coverage_pct": None,
    }
    assert "no_independent_field_validation" in result["limitations"]
    json.dumps(result, allow_nan=False)


def test_equation_fallback_does_not_claim_calibration(features):
    result = agb_model.SAHOOLAGBModel().predict(features)

    assert_uncalibrated(result)
    assert result["method"] == "equation4-heuristic"
    assert result["training_provenance"]["source"] == "not_trained"
    assert result["training_metrics"] is None
    assert "heuristic_coefficients_not_calibrated" in result["limitations"]
    # Preserve the existing research point estimate and fixed harvest-index conversion.
    assert result["agb_t_ha"] == 40.0
    assert result["yield_t_ha"] == 16.0
    assert result["total_agb_t"] == 940.0
    assert result["total_yield_t"] == 376.0


def test_no_sklearn_keeps_an_honest_fallback(monkeypatch, features):
    monkeypatch.setattr(agb_model, "HAS_SKLEARN", False)
    model = agb_model.SAHOOLAGBModel()

    assert model.train_synthetic() is False
    result = model.predict(features)
    assert_uncalibrated(result)
    assert result["method"] == "equation4-heuristic"
    assert result["training_provenance"]["source"] == "not_trained"


def test_synthetic_forest_labels_its_source_and_lack_of_validation(synthetic_model, features):
    model, _ = synthetic_model
    result = model.predict(features)

    assert_uncalibrated(result)
    assert result["method"] == "random-forest-sklearn"
    assert result["training_provenance"] == {
        "source": "synthetic",
        "generator": "equation4_heuristic_plus_gaussian_noise",
        "n_samples": 500,
        "seed": 42,
        "field_observations": 0,
    }
    assert "training_data_are_synthetic" in result["limitations"]
    assert result["agb_t_ha"] == 25.0
    assert result["yield_t_ha"] == 10.0
    assert result["total_agb_t"] == 587.5
    assert result["total_yield_t"] == 235.0


def test_fit_scores_are_resubstitution_not_validation(synthetic_model, features):
    model, metrics = synthetic_model

    assert metrics["evaluation_split"] == "training_resubstitution"
    assert metrics["prediction_stage"] == "unclipped_estimator"
    assert metrics["target_source"] == "synthetic_equation4_heuristic"
    assert metrics["held_out_samples"] == 0
    assert metrics["field_observations"] == 0
    assert metrics["n_samples"] == 500
    assert metrics["rmse_unit"] == "t/ha"
    assert isinstance(metrics["r2"], float)
    assert isinstance(metrics["rmse"], float)
    result = model.predict(features)
    assert result["training_metrics"] == metrics
    assert result["model_accuracy"] is None


def test_paper_numbers_are_an_unverified_reference_only(features):
    result = agb_model.SAHOOLAGBModel().predict(features)

    assert result["model_accuracy"] is None
    reference = result["legacy_paper_reference"]
    assert reference["status"] == "unverified_reference"
    assert reference["applies_to_this_model"] is False
    assert reference["r2"] == 0.89
    assert reference["rmse_t_ha"] == 9.1
    assert reference["paper"] == "Plant Methods 2023"
    assert result["training_metrics"] is None


def test_prediction_metadata_cannot_rewrite_future_evidence(synthetic_model, features):
    model, _ = synthetic_model
    first = model.predict(features)
    first["training_provenance"]["source"] = "field_measurements"
    first["training_metrics"]["evaluation_split"] = "independent_validation"
    first["legacy_paper_reference"]["status"] = "verified"
    first["prediction_interval"]["coverage_pct"] = 85

    again = model.predict(features)
    assert again["training_provenance"]["source"] == "synthetic"
    assert again["training_metrics"]["evaluation_split"] == "training_resubstitution"
    assert again["legacy_paper_reference"]["status"] == "unverified_reference"
    assert_uncalibrated(again)


def test_returned_fit_metrics_cannot_relabel_the_model(synthetic_model, features):
    model, metrics = synthetic_model
    original_split = metrics["evaluation_split"]
    try:
        metrics["evaluation_split"] = "independent_validation"
        result = model.predict(features)
        assert result["training_metrics"]["evaluation_split"] == "training_resubstitution"
    finally:
        metrics["evaluation_split"] = original_split


@pytest.mark.parametrize("tree_values", [(12.0, 12.0), (0.0, 40.0)])
def test_tree_dispersion_cannot_establish_coverage_or_provenance(
    monkeypatch, features, tree_values
):
    # Exercise prediction semantics even where optional sklearn is unavailable.
    # These are deliberately uncontrolled trees, not a fitted or validated forest.
    import numpy as np

    class Tree:
        def __init__(self, value):
            self.value = value

        def predict(self, _):
            return [self.value]

    class Forest:
        estimators_ = [Tree(value) for value in tree_values]

    class Scaler:
        def transform(self, rows):
            return rows

    monkeypatch.setattr(agb_model, "HAS_SKLEARN", False)
    model = agb_model.SAHOOLAGBModel()
    monkeypatch.setattr(agb_model, "HAS_SKLEARN", True)
    monkeypatch.setattr(agb_model, "np", np, raising=False)
    model._trained = True
    model._rf_model = Forest()
    model._scaler = Scaler()
    # An imported/legacy forest without stored provenance must stay unknown.
    model.__dict__.pop("_training_provenance", None)
    model.__dict__.pop("_training_metrics", None)

    result = model.predict(features)

    assert_uncalibrated(result)
    assert result["training_provenance"]["source"] == "unknown"
    assert result["training_provenance"]["n_samples"] is None
    assert result["training_provenance"]["field_observations"] is None
    assert result["training_metrics"] is None
    assert "training_provenance_unknown" in result["limitations"]
    assert "training_data_are_synthetic" not in result["limitations"]
    assert result["agb_t_ha"] == sum(tree_values) / len(tree_values)


def test_singleton_identifies_synthetic_resubstitution(monkeypatch, capsys, features):
    assert agb_model.HAS_SKLEARN, "RF fitting needs the declared scikit-learn test dependency"
    monkeypatch.setattr(agb_model, "_agb_model", None)

    model = agb_model.get_agb_model()
    result = model.predict(features)
    message = capsys.readouterr().out

    assert "synthetic" in message
    assert "training resubstitution" in message
    assert "no field validation" in message
    assert_uncalibrated(result)
    assert model is agb_model.get_agb_model()


def test_cli_handles_unavailable_intervals_without_claiming_coverage(monkeypatch, capsys):
    original_import = builtins.__import__

    def without_sklearn(name, *args, **kwargs):
        if name == "sklearn" or name.startswith("sklearn."):
            raise ImportError("Deliberately exercise the optional-dependency fallback")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_sklearn)
    runpy.run_path(str(Path(agb_model.__file__)), run_name="__main__")
    output = capsys.readouterr().out

    assert "CI 85%" not in output
    assert "(calibrated linear model)" not in output
    assert "الدقة المرجعية (الورقة)" not in output
    assert "research" in output.lower()
    assert "unavailable (uncalibrated)" in output
    assert "unverified reference" in output
