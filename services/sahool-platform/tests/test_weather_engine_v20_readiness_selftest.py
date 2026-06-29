"""V20 — readiness and local self-test probes for weather engine."""

from __future__ import annotations

import pytest
from fastapi import Response

pytestmark = pytest.mark.unit


def test_weather_manifest_advertises_readiness_endpoints():
    from api.routers.weather import weather_layers_manifest

    manifest = weather_layers_manifest()
    endpoints = set(manifest["observability_endpoints"])
    assert "/api/v1/weather/readyz" in endpoints
    assert "/api/v1/weather/self-test" in endpoints
    assert "/api/v1/weather/health" in endpoints


def test_weather_self_test_passes_without_external_io():
    from api.routers import weather

    response = Response()
    result = weather.weather_self_test(response)

    assert response.status_code in (200, None)
    assert result["status"] == "ok"
    assert result["checks"]["tile_center"] is True
    assert result["checks"]["operation_engine"] is True
    assert result["checks"]["prometheus_export"] is True
    assert result["checks"]["cache_accounting"] is True


def test_weather_readyz_returns_ready_when_local_checks_pass(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    monkeypatch.setattr(openmeteo, "openmeteo_breaker_state", lambda: {"state": "closed"})

    response = Response()
    result = weather.weather_readyz(response)

    assert response.status_code in (200, None)
    assert result["status"] == "ready"
    assert result["self_checks"]["status"] == "ok"
    assert result["degraded_reasons"] == []


def test_weather_readyz_degrades_when_breaker_is_open(monkeypatch):
    from api.connectors import openmeteo
    from api.routers import weather

    monkeypatch.setattr(openmeteo, "openmeteo_breaker_state", lambda: {"state": "open"})

    response = Response()
    result = weather.weather_readyz(response)

    assert response.status_code == 503
    assert result["status"] == "degraded"
    assert "openmeteo_breaker_open" in result["degraded_reasons"]
