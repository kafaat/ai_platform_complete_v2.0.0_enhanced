"""V26 — weather runtime smoke plan + operator assets tests."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[3]


def test_weather_manifest_advertises_runtime_smoke_plan():
    from api.routers.weather import weather_layers_manifest

    manifest = weather_layers_manifest()
    endpoints = set(manifest["observability_endpoints"])
    assert "/api/v1/weather/runtime-smoke-plan" in endpoints


def test_weather_runtime_contract_includes_smoke_plan_endpoint():
    from api.routers import weather

    result = weather._weather_runtime_contract()
    paths = {item["path"] for item in result["endpoints"]}
    assert result["status"] == "ok"
    assert "/api/v1/weather/runtime-smoke-plan" in paths


def test_weather_runtime_smoke_plan_is_operator_ready():
    from api.routers import weather

    result = weather.weather_runtime_smoke_plan()
    assert result["status"] == "ok"
    assert result["no_external_io"] is True
    critical = {item["path"] for item in result["critical_endpoints"]}
    assert "/api/v1/weather/readyz" in critical
    assert "/api/v1/weather/runtime-contract" in critical
    assert "/api/v1/weather/env-doctor" in critical
    assert "/api/v1/weather/metrics.prom" in critical
    assert any("weather_runtime_smoke.py" in cmd for cmd in result["commands"])
    assert any("e2e:weather-smoke" in cmd for cmd in result["commands"])


def test_weather_runtime_smoke_script_exists_and_checks_control_plane():
    script = ROOT / "scripts" / "weather_runtime_smoke.py"
    text = script.read_text(encoding="utf-8")
    assert "--base-url" in text
    assert "/api/v1/weather/readyz" in text
    assert "/api/v1/weather/runtime-smoke-plan" in text
    assert "/api/v1/weather/metrics.prom" in text
    assert "include-external" in text


def test_weather_playwright_smoke_spec_is_mocked_and_contract_focused():
    spec = ROOT / "frontend" / "e2e" / "weather-maphub-smoke.spec.ts"
    text = spec.read_text(encoding="utf-8")
    assert "page.route('**/api/v1/weather/layers'" in text
    assert "interpolation=grid" in text
    assert "/api/v1/weather/action-recommendation" in text
    assert "/api/v1/weather/tasks/from-operation-plan" in text
    assert "/api/v1/weather/recommendations/from-operation-plan" in text
