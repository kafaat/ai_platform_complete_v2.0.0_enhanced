"""Field-operation advice on modelled surface moisture: one set of thresholds, two services.

Before: the platform's ``_operation_suitability`` called the surface "dry for sowing" below
0.18 m³/m³ and flagged irrigation need below 0.20, while weather-service said "too dry"
below 0.12 and "irrigation need" below 0.18 — the same Open-Meteo 1–3 cm value gave two
answers depending on which service the client happened to reach. Both now read
``shared/contracts/soil/moisture_policy`` and label the value as modelled surface moisture.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_PLATFORM = _ROOT / "services" / "sahool-platform"
_WEATHER_OPS = _ROOT / "services" / "weather-service" / "operations.py"
_PLATFORM_WEATHER = _PLATFORM / "api" / "routers" / "weather.py"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from shared.contracts.soil import moisture_policy as mp  # noqa: E402


def _weather_service_ops():
    # Loaded by path: the module name ``operations`` is too generic to put its dir on sys.path.
    spec = importlib.util.spec_from_file_location("_ws_operations_parity", _WEATHER_OPS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _platform_suitability():
    pytest.importorskip("fastapi")
    from api.routers.weather import _operation_suitability

    return _operation_suitability


def test_both_services_bind_the_shared_constants():
    ops = _weather_service_ops()
    assert ops.SURFACE_MOISTURE_DRY_M3M3 is mp.SURFACE_MOISTURE_DRY_M3M3
    assert ops.SURFACE_MOISTURE_WET_M3M3 is mp.SURFACE_MOISTURE_WET_M3M3
    tree = ast.parse(_PLATFORM_WEATHER.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "shared.contracts.soil.moisture_policy"
        for alias in node.names
    }
    assert {
        "SURFACE_MOISTURE_DRY_M3M3",
        "SURFACE_MOISTURE_WET_M3M3",
        "MODELLED_SURFACE_MOISTURE_SOURCE",
    } <= imported


def _soil_m_literal_comparisons(source: str, func: str, var: str) -> list[float]:
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func)
    found = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Compare):
            names = [node.left, *node.comparators]
            if any(isinstance(n, ast.Name) and n.id == var for n in names):
                found += [
                    n.value
                    for n in names
                    if isinstance(n, ast.Constant) and isinstance(n.value, float)
                ]
    return found


def test_no_soil_moisture_threshold_literal_left_in_either_service():
    platform = _PLATFORM_WEATHER.read_text(encoding="utf-8")
    ws = _WEATHER_OPS.read_text(encoding="utf-8")
    assert _soil_m_literal_comparisons(platform, "_operation_suitability", "soil_m") == []
    assert _soil_m_literal_comparisons(ws, "operation_suitability", "soil_moisture") == []


def _ws_sample(sm):
    return {
        "temperature_c": 22.0,
        "humidity_pct": 50.0,
        "wind_speed_10m_kmh": 5.0,
        "precipitation_mm": 0.0,
        "soil_temperature_6cm_c": 20.0,
        "soil_moisture_1_to_3cm_m3m3": sm,
    }


def _pf_sample(sm):
    return {
        "temperature_2m_c": 22.0,
        "relative_humidity_2m_pct": 50.0,
        "wind_speed_10m_kmh": 5.0,
        "precipitation_mm": 0.0,
        "soil_temperature_6cm_c": 20.0,
        "soil_moisture_1_to_3cm_m3m3": sm,
    }


_DRY = mp.SURFACE_MOISTURE_DRY_M3M3
_WET = mp.SURFACE_MOISTURE_WET_M3M3


@pytest.mark.parametrize("sm", [_DRY - 0.01, _DRY, _DRY + 0.01])
def test_sowing_dry_verdict_agrees(sm):
    ws = _weather_service_ops().operation_suitability(_ws_sample(sm), "sowing")
    pf = _platform_suitability()(_pf_sample(sm), "sowing")
    ws_dry = "soil_too_dry" in ws["limiting_factors"]
    pf_dry = "soil_moisture_low" in pf["limiting_factors"]
    assert ws_dry == pf_dry == (sm < _DRY)


@pytest.mark.parametrize("sm", [_DRY - 0.01, _DRY, _DRY + 0.01])
def test_irrigation_need_verdict_agrees(sm):
    ws = _weather_service_ops().operation_suitability(_ws_sample(sm), "irrigation")
    pf = _platform_suitability()(_pf_sample(sm), "irrigation")
    assert ("soil_moisture_low" in ws["limiting_factors"]) == (sm < _DRY)
    assert ("soil_moisture_low" in pf["limiting_factors"]) == (sm < _DRY)


@pytest.mark.parametrize("sm", [_WET - 0.01, _WET, _WET + 0.01])
def test_wet_threshold_is_the_same_value(sm):
    ws = _weather_service_ops().operation_suitability(_ws_sample(sm), "irrigation")
    pf = _platform_suitability()(_pf_sample(sm), "harvesting")
    assert ("soil_already_wet" in ws["limiting_factors"]) == (sm > _WET)
    assert ("soil_too_wet" in pf["limiting_factors"]) == (sm > _WET)


def test_outputs_label_the_value_as_modelled_surface_moisture():
    ws = _weather_service_ops().operation_suitability(_ws_sample(0.25), "sowing")
    pf = _platform_suitability()(_pf_sample(0.25), "sowing")
    assert ws["soil_moisture_source"] == pf["soil_moisture_source"]
    assert ws["soil_moisture_source"] == mp.MODELLED_SURFACE_MOISTURE_SOURCE
    assert "modelled" in mp.MODELLED_SURFACE_MOISTURE_SOURCE
    # No value ⇒ no source claimed.
    ws_none = _weather_service_ops().operation_suitability(_ws_sample(None), "sowing")
    pf_none = _platform_suitability()(_pf_sample(None), "sowing")
    assert ws_none["soil_moisture_source"] is None
    assert pf_none["soil_moisture_source"] is None
