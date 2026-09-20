"""Cold embedding failures are bounded; empty pixels never become observations."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def seed_module(monkeypatch):
    directory = ROOT / "services/qdrant-seed"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("v25_seed", directory / "seed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    return module


@pytest.mark.parametrize("failure", ["timeout", "503", "401", "persistent"])
async def test_embedding_retries_transient_failures_but_not_auth(monkeypatch, failure):
    module = seed_module(monkeypatch)
    calls = []

    def respond(request):
        calls.append(request)
        if failure == "persistent" or (failure == "timeout" and len(calls) == 1):
            raise httpx.ReadTimeout("cold load", request=request)
        if len(calls) == 1 and failure in {"503", "401"}:
            return httpx.Response(int(failure))
        return httpx.Response(200, json={"embedding": [0.1, 0.2]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        if failure == "401":
            with pytest.raises(httpx.HTTPStatusError):
                await module._embed("fixture", client)
            assert len(calls) == 1
        elif failure == "persistent":
            with pytest.raises(httpx.ReadTimeout):
                await module._embed("fixture", client)
            assert len(calls) == 3
        else:
            assert await module._embed("fixture", client) == [0.1, 0.2]
            assert len(calls) == 2
            assert calls[0].extensions["timeout"]["read"] == 180


@pytest.mark.parametrize("vector", [[], [True], ["0.1"], {"x": 1}, [None]])
async def test_embedding_malformed_vectors_are_never_written(monkeypatch, vector):
    module = seed_module(monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"embedding": vector}))
    ) as client:
        with pytest.raises(ValueError, match="invalid embedding"):
            await module._embed("fixture", client)
    module.asyncio.sleep.assert_not_awaited()


@pytest.mark.parametrize(
    "ratio,expected",
    [(None, False), (0, False), (0.2, True), (1, True), (True, False), (float("nan"), False)],
)
def test_grid_quality_requires_measured_positive_pixels(monkeypatch, ratio, expected):
    monkeypatch.syspath_prepend(str(ROOT / "services/raster-service"))
    from raster_indicator_product import eligible_observation_product, from_grid_response

    result = from_grid_response(
        {
            "field_id": "f",
            "index": "ndvi",
            "date": "2026-09-19",
            "real_data": True,
            "valid_pixel_ratio": ratio,
        }
    )
    assert result["quality_gate_passed"] is expected
    assert result["real_data"] is True  # a real file can still contain no observation
    envelope = eligible_observation_product({"real_data": True, "indicator_product": result})
    assert (envelope is not None) is expected


@pytest.mark.parametrize(
    "provider,enabled,expected",
    [
        ("local", "true", "completed"),
        ("local", "false", "not_requested"),
        ("vllm", "true", "not_requested"),
    ],
)
async def test_startup_preloads_only_enabled_local_model_without_user_data(
    monkeypatch, provider, enabled, expected
):
    from services.ai_agronomist import ai_generation

    monkeypatch.setenv("AI_PROVIDER", provider)
    monkeypatch.setenv("AI_GENERATION_ENABLED", enabled)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"done": True})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(respond), **kw)
    )
    result = await ai_generation.preload_local_generation()
    assert result["status"] == expected
    assert len(requests) == (1 if expected == "completed" else 0)
    if requests:
        import json

        payload = json.loads(requests[0].content)
        assert set(payload) == {"model", "prompt", "stream"}
        assert payload["prompt"] == "" and payload["stream"] is False
        assert requests[0].url.path == "/api/generate"
