"""V22 — weather runtime contract + env doctor tests."""

from __future__ import annotations

import pytest
from fastapi import Response

pytestmark = pytest.mark.unit


def test_weather_manifest_advertises_runtime_contract_and_env_doctor():
    from api.routers.weather import weather_layers_manifest

    manifest = weather_layers_manifest()
    endpoints = set(manifest["observability_endpoints"])
    assert "/api/v1/weather/runtime-contract" in endpoints
    assert "/api/v1/weather/env-doctor" in endpoints


def test_weather_runtime_contract_checks_api_and_frontend_contract():
    from api.routers import weather

    response = Response()
    result = weather.weather_runtime_contract(response)

    assert response.status_code in (200, None)
    assert result["status"] == "ok"
    assert result["missing_endpoints"] == []
    assert result["guards"]["rate_limit_enabled"] is True
    assert result["guards"]["action_bridge_enabled"] is True
    expected_actions = result["frontend_contract"]["expected_probe_actions"]
    assert "/api/v1/weather/action-recommendation" in expected_actions
    assert "/api/v1/weather/tasks/from-operation-plan" in expected_actions
    assert "/api/v1/weather/recommendations/from-operation-plan" in expected_actions


def test_weather_env_doctor_reports_safe_local_defaults():
    from api.routers import weather

    response = Response()
    result = weather.weather_env_doctor(response)

    assert response.status_code in (200, None)
    assert result["status"] == "ok"
    assert result["failed"] == []
    assert result["checks"]["cache_ttl_valid"] is True
    assert result["checks"]["rate_limits_valid"] is True
    assert result["checks"]["runtime_contract_ok"] is True
    assert "GET /api/v1/weather/runtime-contract" in result["recommended_runtime_checks"]


def test_weather_runtime_contract_detects_missing_guard(monkeypatch):
    from api.routers import weather

    original = dict(weather._WEATHER_RATE_LIMITS)
    monkeypatch.setattr(weather, "_WEATHER_RATE_LIMITS", {"default": (300, 60)})
    response = Response()
    result = weather.weather_runtime_contract(response)

    assert response.status_code == 500
    assert result["status"] == "degraded"
    assert result["guards"]["rate_limit_enabled"] is False
    weather._WEATHER_RATE_LIMITS.clear()
    weather._WEATHER_RATE_LIMITS.update(original)
