"""Pure candidate-gate tests; not Decision Service production activation evidence."""

import math

import pytest

from shared.mlops import apply_model_promotion, register_model_version

pytestmark = pytest.mark.unit


def _model(metric=0.8, status="candidate"):
    return {
        "model_id": "candidate",
        "task": "agronomic_recommendation",
        "artifact_hash": "a" * 64,
        "status": status,
        "metrics": {"score": metric},
    }


def test_finite_challenger_improvement_succeeds_for_candidate_only():
    result = apply_model_promotion(
        alias="shadow:yield",
        champion={**_model(0.6), "model_id": "champion"},
        challenger=_model(0.65),
    )
    assert result["decision"] == "promote" and result["reasons"] == ["policy_passed"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "abc", None])
def test_missing_and_nonfinite_challenger_scores_fail_closed(value):
    result = apply_model_promotion(
        alias="shadow:yield",
        champion={**_model(0.6), "model_id": "champion"},
        challenger=_model(value),
    )
    assert result["decision"] == "blocked"
    assert "challenger_primary_metric_missing_or_nonfinite" in result["reasons"]
    assert result["metric_delta"]["score"] is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), None])
def test_bad_champion_metric_cannot_be_used_as_implicit_zero(bad):
    r = apply_model_promotion(alias="shadow:yield", champion=_model(bad), challenger=_model(0.9))
    assert r["decision"] == "blocked"
    assert "champion_primary_metric_missing_or_nonfinite" in r["reasons"]


@pytest.mark.parametrize("value", [-1, -float("inf"), float("nan"), None])
def test_invalid_policy_threshold_rejected(value):
    result = apply_model_promotion(
        alias="shadow:yield",
        champion=_model(0.5),
        challenger=_model(0.9),
        policy={"primary_metric": "score", "min_improvement": value},
    )
    assert result["decision"] == "blocked"
    assert "min_improvement_invalid" in result["reasons"]


def test_lower_is_better_uses_correct_direction_for_mae():
    old, new = _model(0.7), _model(0.4)
    old["metrics"], new["metrics"] = {"mae": 0.7}, {"mae": 0.4}
    outcome = apply_model_promotion(
        alias="shadow:soil",
        champion=old,
        challenger=new,
        policy={"primary_metric": "mae", "lower_is_better": True, "min_improvement": 0.2},
    )
    assert outcome["decision"] == "promote"
    regression = apply_model_promotion(
        alias="shadow:soil",
        champion=new,
        challenger=old,
        policy={"primary_metric": "mae", "lower_is_better": True, "min_improvement": 0.2},
    )
    assert regression["decision"] == "blocked"


def test_boolean_direction_is_required():
    result = apply_model_promotion(
        alias="shadow:soil",
        champion=_model(0.5),
        challenger=_model(0.9),
        policy={"primary_metric": "score", "lower_is_better": "false"},
    )
    assert result["decision"] == "blocked"
    assert "metric_direction_invalid" in result["reasons"]


def test_task_mismatch_is_not_agronomic_performance_comparison():
    old = _model(0.5)
    new = _model(0.9)
    new["task"] = "disease_segmentation"
    r = apply_model_promotion(alias="shadow:any", champion=old, challenger=new)
    assert r["decision"] == "blocked"
    assert "model_task_mismatch" in r["reasons"]


@pytest.mark.parametrize("metric", [float("inf"), -float("inf"), float("nan"), True])
def test_model_version_registry_rejects_invalid_metric(metric):
    with pytest.raises(ValueError, match="model_metrics_must_be_finite"):
        register_model_version(
            model_name="yield",
            version="v1",
            task="yield",
            artifacts={"uri": "minio://test/model"},
            metrics={"mae": metric},
        )


def test_phase10_model_register_maps_invalid_metrics_to_422():
    from api.phase10_continuous_learning import ModelRegisterRequest, model_register
    from fastapi import HTTPException

    request = ModelRegisterRequest(
        model_name="soil",
        version="v1",
        task="prediction",
        artifacts={"uri": "minio://models/soil"},
        metrics={"mae": float("inf")},
    )
    with pytest.raises(HTTPException) as exc:
        model_register(request)
    assert exc.value.status_code == 422
