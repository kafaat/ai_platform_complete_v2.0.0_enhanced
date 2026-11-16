"""V20 — readiness and local self-test probes for weather engine."""

from __future__ import annotations

import pytest
from fastapi import Response

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _unobserved_weather_service():
    """Readiness now carries the weather-service health observed in this process (W1-22);
    other tests in the same worker may have recorded failures, so each test starts clean."""
    from api.weather_service_client import reset_observed_weather_service_health

    reset_observed_weather_service_health()
    yield
    reset_observed_weather_service_health()


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


def test_weather_readyz_returns_ready_when_local_checks_pass():
    from api.routers import weather

    response = Response()
    result = weather.weather_readyz(response)

    assert response.status_code in (200, None), "ready probe must not fail on local checks"
    assert result["status"] == "ready", f"readiness degraded: {result['degraded_reasons']}"
    assert result["self_checks"]["status"] == "ok", "self-checks must pass without I/O"
    assert result["degraded_reasons"] == [], "no degraded reason expected"


def test_weather_readiness_declares_the_breaker_delegated_to_weather_service(monkeypatch):
    """W1-22 — the platform no longer calls Open-Meteo, so its in-process connector breaker
    sees no request and would read "closed" forever. Readiness must not present that as a
    measured provider state: it declares the breaker delegated to weather-service, and the
    connector's breaker cannot change platform readiness in either direction."""
    from api.connectors import openmeteo
    from api.routers import weather

    monkeypatch.setattr(openmeteo, "openmeteo_breaker_state", lambda: {"state": "open"})

    response = Response()
    result = weather.weather_readyz(response)

    assert (result["breaker"]["state"], result["breaker"]["owner"]) == (
        "delegated",
        "weather-service",
    ), f"readiness must declare the breaker delegated, got {result['breaker']}"
    assert result["breaker"]["observed"]["source"] == "observed_by_platform", (
        "the delegated breaker must carry the health the platform observed"
    )
    assert "openmeteo_breaker_open" not in result["degraded_reasons"], (
        "the unused platform connector breaker must not drive platform readiness"
    )
    assert weather.weather_health()["breaker"]["state"] == "delegated", (
        "health must declare the same delegated breaker"
    )


def test_weather_readyz_degrades_when_local_self_checks_fail(monkeypatch):
    from api.routers import weather

    monkeypatch.setattr(
        weather,
        "_weather_engine_self_checks",
        lambda: {"status": "degraded", "passed": 0, "failed": ["tile_center"], "checks": {}},
    )

    response = Response()
    result = weather.weather_readyz(response)

    assert response.status_code == 503, "a failed self-check must make readiness 503"
    assert result["status"] == "degraded", "readiness must report degraded"
    assert "self_checks_failed" in result["degraded_reasons"], "the reason must be named"
