from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
MAP_PATH = ROOT / "docs" / "architecture" / "platform_extraction_map.json"
METHODS = {"get", "post", "put", "patch", "delete", "api_route"}
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.governance.platform_route_budget import is_infrastructure_route  # noqa: E402


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
                        routes.append(f"{rel}::{method} {route_path}::{node.name}")
    return sorted(routes)


def test_every_platform_route_has_explicit_target_owner():
    baseline = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    owned = {r["route_key"] for r in baseline["routes"] if r.get("target_owner")}
    current = set(_current_platform_routes())
    missing = sorted(current - owned)
    assert not missing, (
        "New/unowned platform routes must be added to docs/architecture/PLATFORM_EXTRACTION_MAP.md: "
        + repr(missing[:20])
    )


def test_platform_route_budget_does_not_grow():
    baseline = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    raw_routes = _current_platform_routes()
    domain_routes = []
    infrastructure_routes = []
    for route_key in raw_routes:
        # route key: api/file.py::METHOD /path::function
        method_path = route_key.split("::", 2)[1]
        method, path = method_path.split(" ", 1)
        target = infrastructure_routes if is_infrastructure_route(method, path) else domain_routes
        target.append(route_key)
    current_count = len(domain_routes)
    assert len(raw_routes) == len(domain_routes) + len(infrastructure_routes)
    assert any("GET /runtime-identity" in key for key in infrastructure_routes)
    assert current_count <= int(baseline["baseline_route_count"]), (
        f"sahool-platform domain route count grew from {baseline['baseline_route_count']} to {current_count} "
        f"(raw={len(raw_routes)}, infrastructure={len(infrastructure_routes)}). "
        "Add new domain endpoints to their owner service, not to sahool-platform, or update the domain budget deliberately."
    )
