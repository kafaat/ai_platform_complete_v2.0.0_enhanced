from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
MAP_PATH = ROOT / "docs" / "architecture" / "platform_extraction_map.json"
ALLOWLIST_PATH = ROOT / "docs" / "architecture" / "raster_boundary_allowlist.json"
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


def _is_rasterish(route: dict, keywords: list[str]) -> bool:
    haystack = " ".join([route["file"], route["function"], route["path"]]).lower()
    return any(k.lower() in haystack for k in keywords)


def _load_simple_yaml_tables(path: Path) -> dict[str, dict[str, object]]:
    """Parse the small subset used by db_ownership.yml without PyYAML."""
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


def test_rasterish_platform_routes_are_owned_by_raster_or_explicit_legacy_exception():
    extraction_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    allowlist = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    by_key = {r["route_key"]: r for r in extraction_map["routes"]}
    allowed_files = set(allowlist["allowed_platform_files"])
    keywords = allowlist["raster_keywords"]

    violations = []
    for route in _current_platform_routes():
        if not _is_rasterish(route, keywords):
            continue
        mapped = by_key.get(route["route_key"])
        owner = mapped.get("target_owner") if mapped else None
        if owner == "raster-service":
            continue
        if (
            route["file"] in allowed_files
            and "legacy" in allowlist["allowed_platform_files"][route["file"]]
        ):
            continue
        violations.append({"route": route["route_key"], "owner": owner})

    assert not violations, (
        "Raster-like platform routes must target raster-service or be explicit legacy compatibility exceptions: "
        + repr(violations[:20])
    )


def test_platform_raster_references_stay_in_allowlisted_facade_files():
    allowlist = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    allowed_files = set(allowlist["allowed_platform_files"])
    extra_markers = [
        "RASTER_SERVICE_URL",
        "sahool-raster-service",
        "/api/raster",
        "process-from-stac",
        "indicator-grid",
        "raster_assets",
        "zonal_stats",
        "mark_raster_cache_stale",
        "/v1/fields/{field_id}/available-dates",
        "/v1/fields/{field_id}/imagery",
        "/v1/fields/{field_id}/terrain",
    ]

    offenders = []
    for path in sorted((PLATFORM / "api").rglob("*.py")):
        rel = path.relative_to(PLATFORM).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        has_marker = any(marker in text for marker in extra_markers)
        if has_marker and rel not in allowed_files:
            offenders.append(rel)

    assert not offenders, (
        "Raster references in sahool-platform must stay inside the P1 facade/consumer allowlist: "
        + repr(offenders[:30])
    )


def test_platform_does_not_import_raster_service_internals():
    offenders = []
    for path in sorted((PLATFORM / "api").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        rel = path.relative_to(PLATFORM).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.replace("-", "_")
                    if name.startswith("services.raster") or name.startswith("raster_service"):
                        offenders.append(f"{rel} imports {alias.name!r}")
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").replace("-", "_")
                if module.startswith("services.raster") or module.startswith("raster_service"):
                    offenders.append(f"{rel} imports from {node.module!r}")
    assert not offenders, (
        "Platform must call raster-service through HTTP/contracts, not internal imports: "
        + repr(offenders[:20])
    )


def test_raster_owned_tables_have_single_raster_writer():
    allowlist = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    tables = _load_simple_yaml_tables(DB_OWNERSHIP_PATH)
    rasterish_tables = [
        name
        for name in tables
        if name in allowlist["allowed_raster_tables_read_by_platform"] or name.startswith("raster_")
    ]
    violations = []
    for table in rasterish_tables:
        meta = tables[table]
        if meta.get("owner") != "raster-service" or meta.get("writers") != ["raster-service"]:
            violations.append({"table": table, "meta": meta})
    assert not violations, (
        "Raster-owned tables must have exactly one writer: raster-service: " + repr(violations[:20])
    )
