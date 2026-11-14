"""Actual ASGI edge form and lifecycle regressions; requires service dependencies."""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "services/edge-inference"), str(ROOT)]
spec = importlib.util.spec_from_file_location(
    "entrypoint_contract_edge", ROOT / "services/edge-inference/main.py"
)
edge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edge)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(edge, "AGENT_TOKEN", "local-test-token")
    monkeypatch.setenv("PEST_MODEL_PATH", str(tmp_path / "missing.onnx"))
    monkeypatch.setenv("YIELD_MODEL_PATH", str(tmp_path / "missing-yield.onnx"))
    return TestClient(edge.app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "route,data,field",
    [
        ("pest-detect", {"confidence_threshold": "2"}, "file"),
        ("pest-detect", {"confidence_threshold": "0"}, "file"),
        ("pest-detect", {"confidence_threshold": "nan"}, "file"),
        ("pest-detect", {"confidence_threshold": "inf"}, "file"),
        ("pest-detect", {"field_id": "x" * 51}, "file"),
        ("pest-detect", {"crop": "unsupported"}, "file"),
        ("yield-estimate", {"field_id": "f", "image_count": "0"}, "files"),
        ("yield-estimate", {"field_id": "f", "image_count": "21"}, "files"),
        ("yield-estimate", {"field_id": "f", "growth_stage": "unsupported"}, "files"),
    ],
)
def test_invalid_form_returns_422(client, route, data, field):
    response = client.post(
        "/v1/inference/" + route,
        data=data,
        files={field: ("x.png", b"x", "image/png")},
        headers={"x-agent-token": "local-test-token"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "route,data,field",
    [
        ("pest-detect", {"confidence_threshold": "0.6"}, "file"),
        ("yield-estimate", {"field_id": "f", "image_count": "1"}, "files"),
    ],
)
def test_valid_forms_reach_missing_artifact_gate(client, route, data, field):
    response = client.post(
        "/v1/inference/" + route,
        data=data,
        files={field: ("x.png", b"x", "image/png")},
        headers={"x-agent-token": "local-test-token"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "model_file_missing"


def test_unauthenticated_form_rejected(client):
    response = client.post(
        "/v1/inference/pest-detect", files={"file": ("x.png", b"x", "image/png")}
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "route,data,field",
    [
        ("pest-detect", {"confidence_threshold": "2"}, "file"),
        ("pest-detect", {"crop": "bogus"}, "file"),
        ("yield-estimate", {"field_id": "f", "image_count": "0"}, "files"),
        ("yield-estimate", {"growth_stage": "bogus"}, "files"),
    ],
)
@pytest.mark.parametrize("headers", [{}, {"x-agent-token": "wrong-token"}])
def test_auth_runs_before_form_validation(client, route, data, field, headers):
    """Unauthenticated invalid forms get 401, never a 422 echoing the constraint schema."""
    response = client.post(
        "/v1/inference/" + route,
        data=data,
        files={field: ("x.png", b"x", "image/png")},
        headers=headers,
    )
    assert response.status_code == 401, response.text
    assert "pattern" not in response.text and "less_than" not in response.text


@pytest.mark.parametrize(
    "model,handler",
    [
        ("PestDetectionRequest", "detect_pest"),
        ("YieldEstimationRequest", "estimate_yield"),
    ],
)
def test_form_and_model_constraints_are_one_source(model, handler):
    """Form() params and the request model must carry identical constraints (no drift)."""
    import inspect

    fields = getattr(edge, model).model_fields
    params = inspect.signature(getattr(edge, handler)).parameters
    for name, info in fields.items():
        if name not in params:
            continue
        form = list(map(repr, params[name].default.metadata))
        assert form == list(map(repr, info.metadata)), (model, name, form, info.metadata)


def test_non_numeric_form_rejected_by_framework(client):
    response = client.post(
        "/v1/inference/pest-detect",
        data={"confidence_threshold": "abc"},
        files={"file": ("x.png", b"x", "image/png")},
        headers={"x-agent-token": "local-test-token"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("exit_kind", ["normal", "exception", "cancelled"])
def test_lifespan_cancels_and_awaits_sync_worker(monkeypatch, exit_kind):
    monkeypatch.setattr(edge, "OFFLINE_MODE", False)

    async def run():
        ended = asyncio.Event()

        async def worker():
            try:
                await asyncio.Event().wait()
            finally:
                ended.set()

        monkeypatch.setattr(edge, "_periodic_sync", worker)
        task = None
        try:
            try:
                async with edge.lifespan(edge.app):
                    task = edge.app.state.sync_task
                    await asyncio.sleep(0)
                    if exit_kind == "exception":
                        raise RuntimeError("synthetic body failure")
                    if exit_kind == "cancelled":
                        raise asyncio.CancelledError()
            except (RuntimeError, asyncio.CancelledError):
                pass
            assert task.done() and ended.is_set(), "worker survived lifespan termination"
        finally:
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


def test_offline_lifespan_never_starts_worker(monkeypatch):
    monkeypatch.setattr(edge, "OFFLINE_MODE", True)

    async def unexpected():
        raise AssertionError("offline started sync")

    monkeypatch.setattr(edge, "_periodic_sync", unexpected)
    from fastapi import FastAPI

    app = FastAPI()

    async def run():
        async with edge.lifespan(app):
            assert not hasattr(app.state, "sync_task")

    asyncio.run(run())
