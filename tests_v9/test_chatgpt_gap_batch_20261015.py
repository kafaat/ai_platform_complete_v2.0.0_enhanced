"""Regression witnesses for four SAHOOL source defects in the unified batch."""

import ast
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def src(path):
    return (ROOT / path).read_text(encoding="utf-8")


@pytest.fixture
def om(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "services/sahool-platform"))
    from api.connectors import openmeteo

    return openmeteo


@pytest.mark.parametrize("values", [None, [], [None]])
def test_missing_wind_is_unknown_not_very_good(om, values):
    payload = {"temperature_2m_max": [25.0], "precipitation_sum": [0.0]}
    if values is not None:
        payload["wind_speed_10m_max"] = values
    forecast = om._build_daily(payload, 0, "2026-10-15")
    assert forecast.wind_max_ms is None
    status, reason = om.spraying_condition_score(forecast)
    assert status == "unknown"
    assert "الريح" in reason


@pytest.mark.parametrize(
    "wind,status", [(0.0, "very_good"), (3.0, "good"), (6.0, "bad"), (9.0, "very_bad")]
)
def test_measured_wind_retains_spraying_classification(om, wind, status):
    forecast = om._build_daily(
        {
            "temperature_2m_max": [25.0],
            "precipitation_sum": [0.0],
            "wind_speed_10m_max": [wind],
        },
        0,
        "2026-10-15",
    )
    assert forecast.wind_max_ms == wind
    assert om.spraying_condition_score(forecast)[0] == status


@pytest.mark.parametrize("rain,temperature,status", [(6.0, 25.0, "very_bad"), (0.0, 36.0, "bad")])
def test_missing_wind_does_not_hide_measured_spray_prohibition(om, rain, temperature, status):
    forecast = om._build_daily(
        {
            "temperature_2m_max": [temperature],
            "precipitation_sum": [rain],
        },
        0,
        "2026-10-15",
    )
    assert om.spraying_condition_score(forecast)[0] == status


@pytest.mark.asyncio
async def test_current_and_batch_keep_absent_wind_unknown(om, monkeypatch):
    payload = {"current": {"wind_direction_10m": 90.0}}
    fetch = AsyncMock(return_value=payload)
    monkeypatch.setattr(om, "_fetch_json", fetch)
    assert (await om.fetch_current(15.0, 44.0)).wind_speed_ms is None
    fetch.return_value = [payload, {"current": {"wind_speed_10m": 0.0}}]
    current = await om.fetch_current_batch([(15.0, 44.0), (16.0, 45.0)])
    assert [item.wind_speed_ms for item in current] == [None, 0.0]


def test_notification_logical_event_republication_deduplicates():
    path = "agents/notification/agent.py"
    tree = ast.parse(src(path))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_delivery_key")
    namespace = {"hashlib": __import__("hashlib"), "json": __import__("json")}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), path, "exec"), namespace)
    key = namespace["_delivery_key"]
    a = {"tenant_id": "t1", "user_id": "u1", "event_id": "event-10", "_delivery_id": "s:1"}
    b = {**a, "_delivery_id": "s:99"}
    assert key(a) == key(b)
    assert key(a) != key({**b, "event_id": "event-11"})
    assert key(a) != key({**b, "user_id": "u2"})
    assert key({"user_id": "u1", "_delivery_id": "s:1"}) != key(
        {"user_id": "u1", "_delivery_id": "s:2"}
    )


def test_fields_router_has_single_module_json_import():
    code = src("services/sahool-platform/api/routers/fields.py")
    tree = ast.parse(code)
    json_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "json"
    ]
    assert len(json_imports) == 1
    assert json_imports[0].names[0].asname is None
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "__import__"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "json"
    ]


def test_carbon_dashboard_is_explicitly_not_measured():
    main = src("mobile/sahool_app/lib/screens/dashboard_screen.dart")
    assert "data['carbon']" not in main
    assert "carbon['sequestered_kg']" not in main
    assert "carbon['credit_value_usd']" not in main
    assert "CarbonNotMeasuredCard()" in main
    card = src("mobile/sahool_app/lib/widgets/carbon_not_measured_card.dart")
    assert "غير مقيس" in card
    assert "sequestered_kg" not in card


@pytest.mark.asyncio
async def test_fields_terrain_decodes_json_without_reimporting_per_request(monkeypatch):
    """Exercise the route helper and retain JSON geometry semantics after import cleanup."""
    import builtins
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock

    monkeypatch.syspath_prepend(str(ROOT / "services/sahool-platform"))
    import api.main  # noqa: F401 — initialize router dependency cycle
    from api.routers import fields

    geometry = {"type": "Polygon", "coordinates": [[[44, 15], [45, 15], [45, 16], [44, 15]]]}
    bbox = [44, 15, 45, 16]
    guard = Mock(return_value=SimpleNamespace(bbox=bbox))
    raster = AsyncMock(return_value={"computed": True, "source": "dem"})
    monkeypatch.setattr(fields, "guard_field_geometry", guard)
    monkeypatch.setattr(fields, "raster_get_field_terrain", raster)
    original_import = builtins.__import__
    local_json_imports = []

    def monitor_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "json" and (globals or {}).get("__name__") == fields.__name__:
            local_json_imports.append(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", monitor_import)
    result = await fields._compute_field_terrain_from_dem(
        "field-1", json.dumps(geometry), SimpleNamespace(tenant_id="tenant-1")
    )
    assert result == {"computed": True, "source": "dem"}
    guard.assert_called_once_with(geometry)
    raster.assert_awaited_once_with("field-1", tenant_id="tenant-1", bbox=bbox, timeout_s=20.0)
    assert local_json_imports == [], "JSON is already loaded at module scope"
