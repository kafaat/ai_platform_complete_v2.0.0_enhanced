"""Regression witnesses for four SAHOOL source defects in the unified batch."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def src(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_missing_wind_is_unknown_not_very_good():
    path = "services/sahool-platform/api/connectors/openmeteo.py"
    code = src(path)
    assert 'wind_max_ms=_daily_at(d, "wind_speed_10m_max", i, None)' in code
    assert 'wind_speed_ms=c.get("wind_speed_10m", 0)' not in code
    assert '("الريح", forecast.wind_max_ms)' in code
    assert "wind_max_ms: float | None" in code
    ast.parse(code)


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
    assert key({"user_id": "u1", "_delivery_id": "s:1"}) != key({"user_id": "u1", "_delivery_id": "s:2"})


def test_fields_router_has_single_module_json_import():
    code = src("services/sahool-platform/api/routers/fields.py")
    tree = ast.parse(code)
    json_imports = [
        node for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names if alias.name == "json"
    ]
    assert len(json_imports) == 1
    assert json_imports[0].names[0].asname is None


def test_carbon_dashboard_is_explicitly_not_measured():
    main = src("mobile/sahool_app/lib/screens/dashboard_screen.dart")
    card = src("mobile/sahool_app/lib/widgets/carbon_not_measured_card.dart")
    assert "data['carbon']" not in main
    assert "carbon['sequestered_kg']" not in main
    assert "carbon['credit_value_usd']" not in main
    assert "CarbonNotMeasuredCard()" in main
    assert "غير مقيس" in card
    assert "sequestered_kg" not in card
