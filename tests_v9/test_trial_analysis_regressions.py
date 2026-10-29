"""Experimental-unit, numerical and actual HTTP contracts for trial analysis."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ValidationError
from scipy import stats

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "services/sahool-platform/api"


def _load(monkeypatch, name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine(monkeypatch):
    return _load(monkeypatch, "_trial_regression_engine", API / "trial_engine.py")


@pytest.fixture
def models(monkeypatch):
    return _load(monkeypatch, "_trial_regression_models", API / "trial_models.py")


def _blocks(engine, differences=(1, 1, 1, -1)):
    return [
        engine.BlockResult(i + 1, 10 + difference, 10) for i, difference in enumerate(differences)
    ]


def test_legacy_trial_report_asserts_all_conditions(monkeypatch, engine):
    # Keep the legacy report callable without activating unrelated, unmarked
    # tests that mutate cross-service imports. Restore its import path afterward.
    monkeypatch.setattr(sys, "path", sys.path.copy())
    api_package = types.ModuleType("api")
    api_package.__path__ = [str(API)]
    monkeypatch.setitem(sys.modules, "api", api_package)
    monkeypatch.setitem(sys.modules, "api.trial_engine", engine)
    legacy = _load(monkeypatch, "_trial_legacy_report", ROOT / "tests_v9/test_roadmap_phase23.py")
    results = legacy._report_trial_engine()
    assert len(results) == 3
    assert all(status == "✓" for status, _message in results), results


@pytest.mark.parametrize("direction", [1, -1])
def test_valid_paired_results_match_scipy_including_signed_effect_and_interval(engine, direction):
    control = [100, 110, 90, 105, 98, 102]
    treatment = [
        value + direction * delta for value, delta in zip(control, [5, 7, 4, 8, 6, 7], strict=True)
    ]
    blocks = [
        engine.BlockResult(i + 11, t, c)
        for i, (t, c) in enumerate(zip(treatment, control, strict=True))
    ]
    result = engine.analyze_paired_trial(blocks)
    reference = stats.ttest_rel(treatment, control)
    interval = reference.confidence_interval(0.95)

    assert result.n_blocks == len(control)
    assert result.df == len(control) - 1
    assert result.t_statistic == pytest.approx(reference.statistic)
    assert result.p_value == pytest.approx(reference.pvalue)
    assert (result.ci_lower, result.ci_upper) == pytest.approx((interval.low, interval.high))
    assert result.mean_difference * direction > 0
    assert result.is_significant is True
    assert result.statistic_status == "ok"
    assert ("لا تغيير" in result.recommendation_ar) is (direction < 0)


def test_repeating_rows_cannot_manufacture_independent_blocks_or_significance(engine, models):
    blocks = _blocks(engine)
    baseline = engine.analyze_paired_trial(blocks)
    assert baseline.p_value == pytest.approx(0.3910022189557705)
    assert baseline.is_significant is False
    # Previously this exact repetition changed df 3 -> 39 and p to 0.0008726.
    duplicated = blocks * 10
    with pytest.raises(ValueError, match="Duplicate block_number"):
        engine.analyze_paired_trial(duplicated)
    with pytest.raises(ValidationError, match="Duplicate block_number"):
        models.TrialAnalysisRequest(blocks=[asdict(block) for block in duplicated])


@pytest.mark.parametrize("identity", [0, -1, True, 1.0, "1"])
def test_block_identity_requires_a_positive_integer(engine, models, identity):
    blocks = _blocks(engine)
    blocks[0].block_number = identity
    with pytest.raises(ValueError, match="block_number"):
        engine.analyze_paired_trial(blocks)
    with pytest.raises(ValidationError):
        models.TrialAnalysisRequest(blocks=[asdict(block) for block in blocks])


@pytest.mark.parametrize("confidence", [0, 1, -0.1, 1.5, float("nan"), float("inf"), -float("inf")])
def test_confidence_must_be_finite_and_strictly_between_zero_and_one(engine, models, confidence):
    blocks = _blocks(engine)
    with pytest.raises(ValueError, match="confidence_level"):
        engine.analyze_paired_trial(blocks, confidence_level=confidence)
    with pytest.raises(ValidationError):
        models.TrialAnalysisRequest(
            blocks=[asdict(block) for block in blocks], confidence_level=confidence
        )


@pytest.mark.parametrize("field", ["treatment_yield", "control_yield"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_yields_are_rejected_before_inference(engine, models, field, value):
    blocks = _blocks(engine)
    setattr(blocks[0], field, value)
    with pytest.raises(ValueError, match=field):
        engine.analyze_paired_trial(blocks)
    with pytest.raises(ValidationError):
        models.TrialAnalysisRequest(blocks=[asdict(block) for block in blocks])


@pytest.mark.parametrize("difference", [-1, 0, 1])
def test_zero_variance_has_explicit_status_and_strict_json(engine, difference):
    result = engine.analyze_paired_trial(_blocks(engine, [difference] * 4))
    payload = result.to_dict()
    assert type(payload["is_significant"]) is bool
    assert result.mean_difference == difference
    assert (result.ci_lower, result.ci_upper) == (difference, difference)
    if difference:
        assert payload["t_statistic"] is None
        assert payload["statistic_status"] == "zero_variance_difference"
        assert payload["p_value"] == 0
        assert "اصطلاح حدّي" in payload["verdict_ar"]
        assert "تحقّق" in payload["recommendation_ar"]
        assert "يدعم اعتماد" not in payload["recommendation_ar"]
    else:
        assert payload["statistic_status"] == "zero_variance_equal"
        assert payload["t_statistic"] == 0
        assert payload["p_value"] == 1
        assert payload["is_significant"] is False
    assert json.loads(json.dumps(jsonable_encoder(payload), allow_nan=False)) == payload


def test_finite_but_overflowing_yields_fail_as_input_error(engine):
    blocks = [engine.BlockResult(i + 1, 1e308, -1e308) for i in range(4)]
    with pytest.raises(ValueError, match="finite analysis range"):
        engine.analyze_paired_trial(blocks)


def _met_rows(engine, *, identified=True):
    return [
        engine.METObservation(genotype, environment, value, replicate if identified else None)
        for genotype, environment, replicate, value in [
            ("A", "E1", 1, 10),
            ("A", "E1", 2, 12),
            ("A", "E2", 1, 14),
            ("A", "E2", 2, 16),
            ("B", "E1", 1, 11),
            ("B", "E1", 2, 13),
            ("B", "E2", 1, 9),
            ("B", "E2", 2, 11),
        ]
    ]


@pytest.mark.parametrize("extra_value", [10, 100])
def test_met_rejects_duplicate_identified_replicate_even_if_value_changes(engine, extra_value):
    rows = _met_rows(engine)
    rows.append(engine.METObservation(" A ", " E1 ", extra_value, 1))
    with pytest.raises(ValueError, match="Duplicate MET replicate identity"):
        engine.analyze_met(rows)


def test_met_replication_identity_is_scoped_to_genotype_and_environment(engine):
    # The same replicate number in a different genotype/environment is legitimate.
    result = engine.analyze_met(_met_rows(engine))
    assert result.n_observations == 8
    assert result.genotype_means == {"A": 13.0, "B": 11.0}
    assert result.to_dict()["decision_eligible"] is False


def test_met_unlabelled_rows_remain_descriptive_not_automatically_deduplicated(engine):
    rows = _met_rows(engine, identified=False)
    rows.append(engine.METObservation("A", "E1", 10))
    result = engine.analyze_met(rows)
    assert result.n_observations == 9
    assert result.genotype_means["A"] == pytest.approx(((10 + 12 + 10) / 3 + 15) / 2)
    assert result.to_dict()["claim_scope"] == "descriptive_gxe_stability_only"
    assert result.to_dict()["automatic_model_promotion_eligible"] is False


def test_met_overflow_is_an_input_error_not_nonfinite_json(engine):
    rows = [engine.METObservation(g, e, 1e308) for g in ["A", "B"] for e in ["E1", "E2"]]
    with pytest.raises(ValueError, match="finite analysis range"):
        engine.analyze_met(rows)


@pytest.mark.parametrize("replicate", [0, -1, True, 1.5, "1"])
def test_met_explicit_replicate_identity_must_be_a_positive_integer(engine, models, replicate):
    rows = _met_rows(engine)
    rows[0] = engine.METObservation("A", "E1", 10, replicate)
    with pytest.raises(ValueError, match="MET replicate"):
        engine.analyze_met(rows)
    with pytest.raises(ValidationError):
        models.METObservationInput(
            genotype="A", environment_id="E1", yield_value=10, replicate=replicate
        )


def _spatial_plan():
    return {
        "field_geometry": {"type": "Polygon", "coordinates": []},
        "treatments": ["control", "A"],
        "n_blocks": 4,
        "machine_heading_deg": 0,
        "implement_width_m": 3,
        "randomization_seed": "regression",
    }


@pytest.mark.parametrize("trial_id", [None, "", "   ", "unbound-trial"])
def test_spatial_plan_requires_nonblank_trial_reference(engine, models, trial_id):
    with pytest.raises(ValidationError, match="trial_id"):
        models.TrialAnalysisRequest(
            blocks=[asdict(block) for block in _blocks(engine)],
            spatial_plan=_spatial_plan(),
            trial_id=trial_id,
        )


def test_paired_analysis_remains_stateless_and_spatial_reference_is_trimmed(engine, models):
    body = {"blocks": [asdict(block) for block in _blocks(engine)]}
    assert models.TrialAnalysisRequest(**body).trial_id is None
    spatial = models.TrialAnalysisRequest(
        **body, spatial_plan=_spatial_plan(), trial_id=" trial-1 "
    )
    assert spatial.trial_id == "trial-1"


@pytest.fixture
def trial_app(monkeypatch, engine, models):
    # Import the production router without starting api.main's DB/schedulers.
    # monkeypatch restores every replacement, including any pre-existing api.*.
    api_package = types.ModuleType("api")
    api_package.__path__ = [str(API)]
    auth = types.ModuleType("api.main")

    class UserSchema(BaseModel):
        id: int = 1

    async def get_current_user():
        return UserSchema()

    auth.UserSchema = UserSchema
    auth.get_current_user = get_current_user
    for name, module in {
        "api": api_package,
        "api.main": auth,
        "api.trial_engine": engine,
        "api.trial_models": models,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    router = _load(monkeypatch, "_trial_regression_router", API / "routers/trials.py")
    app = FastAPI()
    app.include_router(router.router)
    return app


def _post(app, body):
    async def request():
        # Keep sandboxed event loops responsive to AnyIO worker completion.
        async def wakeup():
            while True:
                await asyncio.sleep(0.01)

        heartbeat = asyncio.create_task(wakeup())
        try:
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://trial.test"
            ) as client:
                return await asyncio.wait_for(
                    client.post(
                        "/api/v1/trials/analyze",
                        content=json.dumps(body),
                        headers={"content-type": "application/json"},
                    ),
                    timeout=5,
                )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    return asyncio.run(request())


@pytest.mark.parametrize(
    "differences", [(1, 1, 1, -1), (1, 1, 1, 1), (-1, -1, -1, -1), (0, 0, 0, 0)]
)
def test_actual_router_returns_json_for_finite_and_zero_variance_analysis(
    engine, trial_app, differences
):
    response = _post(
        trial_app, {"blocks": [asdict(block) for block in _blocks(engine, differences)]}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert type(payload["is_significant"]) is bool
    assert payload["n_blocks"] == 4
    json.dumps(payload, allow_nan=False)
    if len(set(differences)) == 1 and differences[0] != 0:
        assert payload["t_statistic"] is None
        assert payload["statistic_status"] == "zero_variance_difference"
    else:
        assert isinstance(payload["t_statistic"], (int, float))


@pytest.mark.parametrize(
    "case",
    [
        "duplicate",
        "too_few",
        "invalid_id",
        "invalid_confidence",
        "nan",
        "inf",
        "spatial_without_id",
        "met_duplicate",
    ],
)
def test_actual_router_rejects_invalid_analysis_with_422(engine, trial_app, case):
    body = {"blocks": [asdict(block) for block in _blocks(engine)]}
    if case == "duplicate":
        body["blocks"] *= 10
    elif case == "too_few":
        body["blocks"] = body["blocks"][:2]
    elif case == "invalid_id":
        body["blocks"][0]["block_number"] = 0
    elif case == "invalid_confidence":
        body["confidence_level"] = 1.5
    elif case == "nan":
        body["blocks"][0]["treatment_yield"] = float("nan")
    elif case == "inf":
        body["confidence_level"] = float("inf")
    elif case == "spatial_without_id":
        body["spatial_plan"] = _spatial_plan()
    elif case == "met_duplicate":
        body["season_id"] = "season-1"
        rows = _met_rows(engine)
        body["met_observations"] = [asdict(row) for row in [*rows, rows[0]]]
    response = _post(trial_app, body)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]
    json.dumps(response.json(), allow_nan=False)
