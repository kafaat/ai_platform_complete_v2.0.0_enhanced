from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
WEATHER_SERVICE_MAIN = ROOT / "services" / "weather-service" / "main.py"
MAP_PATH = ROOT / "docs" / "architecture" / "platform_extraction_map.json"
ALLOWLIST_PATH = ROOT / "docs" / "architecture" / "weather_boundary_allowlist.json"
DB_OWNERSHIP_PATH = ROOT / "docs" / "architecture" / "db_ownership.yml"
METHODS = {"get", "post", "put", "patch", "delete", "api_route"}


def _decorator_route(dec: ast.AST):
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    method = None
    if isinstance(func, ast.Attribute) and func.attr in METHODS:
        method = func.attr.upper()
    elif isinstance(func, ast.Name) and func.id in METHODS:
        method = func.id.upper()
    if not method:
        return None
    path = "<dynamic>"
    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
        path = dec.args[0].value
    else:
        for kw in dec.keywords:
            if (
                kw.arg == "path"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                path = kw.value.value
                break
    if method == "API_ROUTE":
        methods = []
        for kw in dec.keywords:
            if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                for elt in kw.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        methods.append(elt.value.upper())
        method = ",".join(sorted(methods)) if methods else "API_ROUTE"
    return method, path


def _current_platform_routes():
    routes = []
    for path in sorted((PLATFORM / "api").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        rel = path.relative_to(PLATFORM).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    route = _decorator_route(dec)
                    if route:
                        method, route_path = route
                        routes.append(
                            {
                                "route_key": f"{rel}::{method} {route_path}::{node.name}",
                                "file": rel,
                                "function": node.name,
                                "method": method,
                                "path": route_path,
                            }
                        )
    return routes


def _load_simple_yaml_tables(path: Path) -> dict[str, dict[str, object]]:
    tables: dict[str, dict[str, object]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#") or line.strip() == "tables:":
            continue
        table_match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
        if table_match:
            current = table_match.group(1)
            tables[current] = {}
            continue
        prop_match = re.match(r"^    ([a-z_]+):\s*(.*)$", line)
        if current and prop_match:
            key, value = prop_match.group(1), prop_match.group(2).strip()
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                tables[current][key] = [part.strip() for part in inner.split(",") if part.strip()]
            else:
                tables[current][key] = value.strip('"')
    return tables


def _is_weatherish(route: dict, keywords: list[str]) -> bool:
    haystack = " ".join([route["file"], route["function"], route["path"]]).lower()
    return any(k.lower() in haystack for k in keywords)


def test_weatherish_platform_routes_target_weather_service():
    extraction_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    allowlist = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    by_key = {r["route_key"]: r for r in extraction_map["routes"]}
    keywords = allowlist["weather_route_keywords"]

    violations = []
    for route in _current_platform_routes():
        if not _is_weatherish(route, keywords):
            continue
        mapped = by_key.get(route["route_key"])
        owner = mapped.get("target_owner") if mapped else None
        if owner != "weather-service":
            violations.append({"route": route["route_key"], "owner": owner})

    assert not violations, (
        "Weather-like platform routes must target weather-service in the extraction map: "
        + repr(violations[:30])
    )


def test_platform_weather_runtime_references_stay_in_allowlist():
    allowlist = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    allowed_files = set(allowlist["allowed_platform_files"])
    markers = allowlist["provider_or_runtime_markers"]

    offenders = []
    for path in sorted((PLATFORM / "api").rglob("*.py")):
        rel = path.relative_to(PLATFORM).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(marker in text for marker in markers) and rel not in allowed_files:
            offenders.append(rel)

    assert not offenders, (
        "Weather provider/runtime logic in sahool-platform must stay inside the P1 allowlist: "
        + repr(offenders[:40])
    )


def test_weather_owned_tables_have_single_weather_writer():
    tables = _load_simple_yaml_tables(DB_OWNERSHIP_PATH)
    weatherish = [
        name for name in tables if name.startswith("weather_") or name.startswith("field_weather_")
    ]
    violations = []
    for table in weatherish:
        meta = tables[table]
        if meta.get("owner") != "weather-service" or meta.get("writers") != ["weather-service"]:
            violations.append({"table": table, "meta": meta})
    assert not violations, (
        "Weather-owned tables must have exactly one writer: weather-service: "
        + repr(violations[:20])
    )


def test_weather_service_runtime_contract_is_now_realized():
    text = WEATHER_SERVICE_MAIN.read_text(encoding="utf-8", errors="ignore")
    required = [
        '"mode": "runtime"',
        '"implemented_runtime": True',
        '@app.get("/v1/weather/current")',
        '@app.get("/v1/weather/forecast")',
        '@app.get("/v1/weather/historical")',
        '@app.get("/v1/weather/operation-window")',
        '@app.get("/v1/weather/tile-data/{z}/{x}/{y}")',
        '@app.get("/v1/weather/wind-grid/{z}/{x}/{y}")',
        '@app.get("/contract")',
    ]
    missing = [marker for marker in required if marker not in text]
    assert not missing, (
        "weather-service must expose the P3 runtime contract after realization: " + repr(missing)
    )
