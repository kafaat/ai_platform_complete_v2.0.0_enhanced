"""P3.4 — weather facade neutral fallback + route proxying + client import-safety.

Covers:
  - api.weather_service_client.get_weather_tile_data / get_operation_tile_data return a NEUTRAL
    tile (value=null, available=false) when weather-service is unreachable (502), instead of
    propagating one Bad Gateway per tile — preserving the map "don't flood with 502" guarantee
    across the platform -> weather-service network hop.
  - non-502 upstream errors still propagate (no fabricated values).
  - the platform weather routes are thin facades that return the weather-service payload as-is.
  - neither boundary client imports fastapi at module import time (must stay importable in the
    pure-logic `pytest -m unit` tier which runs without fastapi installed).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from api import weather_service_client as wsc
from fastapi import HTTPException

pytestmark = pytest.mark.unit

PLATFORM = Path(__file__).resolve().parents[1]
CLIENT_FILES = (
    PLATFORM / "api" / "weather_service_client.py",
    PLATFORM / "api" / "raster_service_client.py",
)


@pytest.mark.asyncio
async def test_get_weather_tile_data_returns_neutral_tile_on_502(monkeypatch):
    async def unreachable(*_a, **_k):
        raise HTTPException(status_code=502, detail="weather-service unreachable")

    monkeypatch.setattr(wsc, "weather_get_json", unreachable)
    tile = await wsc.get_weather_tile_data(5, 16, 14, layer="temperature")
    assert tile["tile"] == {"z": 5, "x": 16, "y": 14}
    assert tile["layer"] == "temperature"
    assert tile["value"] is None
    assert tile["sample"] is None
    assert tile["available"] is False
    assert tile["cache_state"] == "service_unavailable"
    assert tile["upstream_error"] == "weather-service unreachable"
    assert tile["rendered_by"] == "sahool-client-gridlayer"


@pytest.mark.asyncio
async def test_get_operation_tile_data_returns_neutral_tile_on_502(monkeypatch):
    async def unreachable(*_a, **_k):
        raise HTTPException(status_code=502, detail="weather-service unreachable")

    monkeypatch.setattr(wsc, "weather_get_json", unreachable)
    tile = await wsc.get_operation_tile_data(5, 16, 14, operation="spraying")
    assert tile["tile"] == {"z": 5, "x": 16, "y": 14}
    assert tile["layer"] == "spraying"
    assert tile["value"] is None
    assert tile["available"] is False
    assert tile["cache_state"] == "service_unavailable"


@pytest.mark.asyncio
async def test_facade_propagates_non_502_errors(monkeypatch):
    """A 400 (bad layer) is a real client error, not an outage — it must not be masked."""

    async def bad_request(*_a, **_k):
        raise HTTPException(status_code=400, detail="unsupported layer")

    monkeypatch.setattr(wsc, "weather_get_json", bad_request)
    with pytest.raises(HTTPException) as exc:
        await wsc.get_weather_tile_data(5, 16, 14, layer="temperature")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_weather_route_proxies_facade_payload(monkeypatch):
    from api.routers import weather

    canned = {
        "tile": {"z": 5, "x": 16, "y": 14},
        "center": {"lat": 15.0, "lon": 44.0},
        "layer": "temperature",
        "value": 21.5,
        "unit": "°C",
        "cache_state": "fresh",
        "source": "open-meteo+sahool-rules",
        "rendered_by": "sahool-client-gridlayer",
    }

    async def fake_facade(
        z, x, y, *, layer, time="now", model="best_match", interpolation="center"
    ):
        assert (z, x, y, layer) == (5, 16, 14, "temperature")
        return canned

    monkeypatch.setattr(weather, "get_weather_tile_data", fake_facade)
    out = await weather.weather_tile_data(
        5, 16, 14, layer="temperature", time="now", model="best_match", interpolation="center"
    )
    assert out is canned


def _has_module_level_fastapi_import(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    for node in tree.body:  # top-level statements only
        if isinstance(node, ast.Import):
            if any("fastapi" in alias.name for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and "fastapi" in node.module:
                return True
    return False


def test_boundary_clients_have_no_module_level_fastapi_import():
    """These clients are reachable from the pure-logic unit tier (which runs without fastapi).
    A module-level fastapi import would break `pytest -m unit` collection — lazy-import it
    inside the functions that raise/catch HTTPException instead."""
    offenders = [p.name for p in CLIENT_FILES if _has_module_level_fastapi_import(p)]
    assert not offenders, f"module-level fastapi import must be lazy inside functions: {offenders}"
