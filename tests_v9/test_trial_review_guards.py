"""Independent review witnesses for numeric and HTTP trial safety."""

import json
from dataclasses import asdict

import pytest
from test_trial_analysis_regressions import (
    API,
    _blocks,
    _load,
    _post,
    engine,
    models,
    trial_app,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def design(monkeypatch):
    return _load(monkeypatch, "_review_design", API.parent / "core/field_trial_design.py")


@pytest.mark.parametrize("value", [True, False])
def test_boolean_yields_rejected_by_engine_and_models(engine, models, value):
    blocks = _blocks(engine)
    blocks[0].treatment_yield = value
    with pytest.raises(ValueError):
        engine.analyze_paired_trial(blocks)
    with pytest.raises(ValueError):
        models.TrialBlockInput(**asdict(blocks[0]))
    with pytest.raises(ValueError):
        models.METObservationInput(genotype="A", environment_id="E", yield_value=value)


@pytest.mark.parametrize("count", [True, 3.5, float("nan"), float("inf"), "4", 0, -1])
def test_block_counts_are_positive_integers(design, count):
    with pytest.raises(ValueError):
        design.design_rcbd(treatments=["control", "A"], n_blocks=count)


@pytest.mark.parametrize("control,treatment", [(1e-308, 10.0), (1e308, 1e308), (-1e308, 1e308)])
def test_descriptive_overflow_is_controlled(design, control, treatment):
    with pytest.raises(ValueError, match="finite|محدود"):
        design.analyze_trial(treatment_results={"control": [control] * 4, "A": [treatment] * 4})


def test_zero_control_preserves_absolute_result_without_fake_percent(engine):
    result = engine.analyze_paired_trial(
        [engine.BlockResult(i + 1, value, 0) for i, value in enumerate([10, 11, 12, 13])]
    )
    body = result.to_dict()
    assert body["percent_change"] is None
    assert body["percent_change_status"] == "zero_control"
    assert body["mean_difference"] == 11.5
    assert body["is_significant"] is True
    assert "0.0%" not in body["verdict_ar"]
    json.dumps(body, allow_nan=False)


@pytest.mark.parametrize("difference", [-1, 0, 1])
def test_degenerate_results_never_signal_ordinary_inference(engine, difference):
    body = engine.analyze_paired_trial(_blocks(engine, [difference] * 4)).to_dict()
    assert body["inferential_valid"] is False
    assert body["requires_review"] is True
    assert body["is_significant"] is False


@pytest.mark.parametrize("case", ["list", "dict", "extra_nan", "nested_nan"])
def test_nested_invalid_requests_return_safe_422(engine, trial_app, case):
    body = {"blocks": [asdict(b) for b in _blocks(engine)]}
    if case == "list":
        body["blocks"][0]["treatment_yield"] = [float("inf")]
    elif case == "dict":
        body["blocks"][0]["treatment_yield"] = {"value": float("inf")}
    elif case == "extra_nan":
        body["blocks"][1]["block_number"] = 1
        body["private_extra"] = float("nan")
    else:
        body["blocks"][0]["treatment_yield"] = {"value": float("nan")}
    response = _post(trial_app, body)
    assert response.status_code == 422, response.text
    details = response.json()["detail"]
    assert details
    assert all(set(error) <= {"type", "loc", "msg"} for error in details)
    json.dumps(response.json(), allow_nan=False)


def test_numeric_overflow_token_and_bounded_diagnostics(engine, trial_app):
    import asyncio
    from contextlib import suppress

    import httpx

    async def post_raw(raw):
        async def wakeup():
            while True:
                await asyncio.sleep(0.01)

        heartbeat = asyncio.create_task(wakeup())
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=trial_app, raise_app_exceptions=False),
                base_url="http://trial.test",
            ) as client:
                return await asyncio.wait_for(
                    client.post(
                        "/api/v1/trials/analyze",
                        content=raw,
                        headers={"content-type": "application/json"},
                    ),
                    5,
                )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    body = {"blocks": [asdict(b) for b in _blocks(engine)]}
    body["blocks"][0]["treatment_yield"] = ["OVERFLOW_TOKEN"]
    raw = json.dumps(body).replace('"OVERFLOW_TOKEN"', "1e309")
    response = asyncio.run(post_raw(raw))
    assert response.status_code == 422
    json.dumps(response.json(), allow_nan=False)
    response = _post(
        trial_app,
        {
            "blocks": [
                {"block_number": 0, "treatment_yield": {}, "control_yield": []} for _ in range(100)
            ]
        },
    )
    assert response.status_code == 422
    assert len(response.json()["detail"]) == 50
    assert all(set(item) == {"type", "loc", "msg"} for item in response.json()["detail"])
