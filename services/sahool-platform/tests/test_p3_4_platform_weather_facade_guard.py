from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
WEATHER_ROUTER = PLATFORM / "api" / "routers" / "weather.py"
WEATHER_CLIENT = PLATFORM / "api" / "weather_service_client.py"
CONTRACT = ROOT / "docs" / "architecture" / "WEATHER_OWNERSHIP_CONTRACT.md"

FACADE_FUNCTIONS = {
    "weather_current": "get_current_weather",
    "weather_forecast": "get_weather_forecast",
    "weather_historical": "get_weather_historical",
    "weather_tile_data": "get_weather_tile_data",
    "weather_operation_tile_data": "get_operation_tile_data",
    "weather_operation_window": "get_operation_window",
    "weather_operation_plan": "get_operation_plan",
    "weather_tile_series": "get_weather_tile_series",
    "weather_tile_cache_stats": "get_tile_cache_stats",
}

FORBIDDEN_IN_FACADE_BODIES = [
    "fetch_current",
    "fetch_daily_forecast",
    "fetch_historical",
    "fetch_weather_tile_data",
    "_operation_suitability",
    "_tile_center",
    "_weather_tile_interpolation_payload",
    "_get_weather_sample_cached",
    "Open-Meteo:",
]


def _functions_by_name(path: Path) -> dict[str, ast.AST]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _source_segment(path: Path, node: ast.AST) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return ast.get_source_segment(text, node) or ""


def test_p3_4_weather_client_exists_and_owns_direct_service_transport():
    text = WEATHER_CLIENT.read_text(encoding="utf-8", errors="ignore")
    assert "DEFAULT_WEATHER_SERVICE_URL" in text
    assert "weather_get_json" in text
    assert "X-Agent-Token" in text
    assert "httpx.AsyncClient" in text
    assert "/v1/weather/current" in text
    assert "/v1/weather/operation-window" in text
    assert "/v1/weather/wind-grid/{z}/{x}/{y}" in text


def test_p3_4_core_weather_platform_routes_are_facades_only():
    functions = _functions_by_name(WEATHER_ROUTER)
    missing = [name for name in FACADE_FUNCTIONS if name not in functions]
    assert not missing

    violations: list[dict[str, object]] = []
    for name, client_call in FACADE_FUNCTIONS.items():
        segment = _source_segment(WEATHER_ROUTER, functions[name])
        if client_call not in segment:
            violations.append({"function": name, "reason": f"missing {client_call}"})
        forbidden = [token for token in FORBIDDEN_IN_FACADE_BODIES if token in segment]
        if forbidden:
            violations.append({"function": name, "forbidden": forbidden})
    assert not violations, repr(violations)


def test_p3_4_weather_router_does_not_open_direct_weather_service_transport():
    text = WEATHER_ROUTER.read_text(encoding="utf-8", errors="ignore")
    forbidden_transport = [
        "WEATHER_SERVICE_URL",
        "sahool-weather-service",
        "http://sahool-weather-service",
    ]
    offenders = [token for token in forbidden_transport if token in text]
    assert not offenders, repr(offenders)


def test_p3_4_contract_documents_platform_weather_facade():
    text = CONTRACT.read_text(encoding="utf-8", errors="ignore")
    assert "P3.4" in text
    assert "api/weather_service_client.py" in text
    assert "weather-service owns" in text
