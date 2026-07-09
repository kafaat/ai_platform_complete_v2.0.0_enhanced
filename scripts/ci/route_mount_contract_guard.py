#!/usr/bin/env python3
"""Guard route-bearing FastAPI services after main.py decomposition.

A zero-route ``main.py`` is acceptable only when it explicitly delegates to
``router_registry.register_routers(app)`` or when it is a documented non-HTTP
worker/bot entrypoint. This prevents dead-code services hidden by stale
inventories that only scan ``main.py`` decorators.
"""

from __future__ import annotations

import ast
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "route_mount_inventory.generated.json"
OUT_CSV = ROOT / "route_mount_inventory.csv"

NON_HTTP_ENTRYPOINT_ALLOWLIST = {
    "services/weather-polygon-worker/src/main.py",
    "services/weather-signal-engine/src/main.py",
    "bots/telegram/main.py",  # aiogram router, not FastAPI
}

ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _route_count(tree: ast.Module) -> int:
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr in ROUTE_METHODS
            ):
                count += 1
    return count


def _route_registration_call_count(tree: ast.Module) -> int:
    """Count programmatic FastAPI registrations like app.get("/path")(handler)."""
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        inner = node.func
        if (
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr in ROUTE_METHODS
        ):
            if (
                inner.args
                and isinstance(inner.args[0], ast.Constant)
                and isinstance(inner.args[0].value, str)
            ):
                count += 1
    return count


def _delegates_to_runtime_module(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("_runtime"):
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("_runtime"):
                    return True
    return False


def _has_fastapi_app(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "FastAPI":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "FastAPI":
                return True
    return False


def _calls_register_routers(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "register_routers":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "register_routers":
                return True
    return False


def _router_py_files(service_root: Path) -> list[Path]:
    routers = service_root / "routers"
    if not routers.is_dir():
        return []
    return sorted(p for p in routers.glob("*.py") if p.name != "__init__.py")


def _router_route_count(service_root: Path) -> int:
    count = 0
    for p in _router_py_files(service_root):
        try:
            count += _route_count(_parse(p))
        except SyntaxError:
            continue
    return count


def _calls_known_app_factory(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "create_raster_app":
                return True
            if isinstance(func, ast.Name) and func.id.endswith("create_app"):
                return True
    return False


def collect() -> list[dict[str, object]]:
    candidates = (
        sorted(ROOT.glob("services/*/main.py"))
        + sorted(ROOT.glob("services/*/src/main.py"))
        + sorted(ROOT.glob("services/sahool-platform/api/main.py"))
        + sorted(ROOT.glob("bots/*/main.py"))
    )
    rows: list[dict[str, object]] = []
    for path in candidates:
        rel = _rel(path)
        if path.parent.name == "src":
            service_root = path.parent.parent
            router_root = service_root
        elif path.parent.name == "api" and path.parent.parent.name == "sahool-platform":
            service_root = path.parent.parent
            router_root = path.parent
        else:
            service_root = path.parent
            router_root = service_root
        try:
            tree = _parse(path)
        except SyntaxError as exc:
            rows.append({"path": rel, "status": "parse_error", "reason": str(exc)})
            continue
        direct_routes = _route_count(tree) + _route_registration_call_count(tree)
        has_fastapi = _has_fastapi_app(tree)
        delegates = _calls_register_routers(tree)
        app_factory = _calls_known_app_factory(tree)
        runtime_delegation = _delegates_to_runtime_module(tree)
        router_routes = _router_route_count(router_root)
        allowed_non_http = rel in NON_HTTP_ENTRYPOINT_ALLOWLIST
        if direct_routes > 0:
            status = "direct_routes"
            reason = "main.py owns direct route handlers"
        elif delegates and router_routes > 0:
            status = "delegated_routes"
            reason = "main.py delegates to router_registry and routers contain routes"
        elif app_factory and router_routes > 0:
            status = "factory_delegated_routes"
            reason = "main.py delegates to an app factory and routers contain routes"
        elif runtime_delegation:
            status = "runtime_delegated_routes"
            reason = "main.py delegates to a runtime module that owns app construction/routes"
        elif allowed_non_http and not has_fastapi:
            status = "non_http_entrypoint"
            reason = "documented worker/bot entrypoint"
        elif has_fastapi and delegates and router_routes == 0:
            status = "broken_delegation"
            reason = "FastAPI service calls register_routers but routers contain zero routes"
        elif has_fastapi:
            status = "unmounted_fastapi"
            reason = "FastAPI app has no direct routes and no router_registry delegation"
        else:
            status = "non_http_unknown"
            reason = "no FastAPI routes detected and not explicitly allowed"
        rows.append(
            {
                "path": rel,
                "service": service_root.name,
                "has_fastapi": has_fastapi,
                "direct_routes": direct_routes,
                "router_routes": router_routes,
                "delegates_to_router_registry": delegates,
                "delegates_to_app_factory": app_factory,
                "delegates_to_runtime_module": runtime_delegation,
                "status": status,
                "reason": reason,
            }
        )
    return rows


def write(rows: list[dict[str, object]]) -> None:
    OUT_JSON.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["path"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    import sys

    check = "--check" in sys.argv
    rows = collect()
    bad = [
        r
        for r in rows
        if r["status"]
        in {"parse_error", "broken_delegation", "unmounted_fastapi", "non_http_unknown"}
    ]
    if bad:
        for r in bad:
            print(f"route mount violation: {r['path']}: {r['status']} - {r['reason']}")
        return 1
    before = OUT_JSON.read_text(encoding="utf-8") if OUT_JSON.exists() else None
    before_csv = OUT_CSV.read_text(encoding="utf-8") if OUT_CSV.exists() else None
    write(rows)
    if check:
        after = OUT_JSON.read_text(encoding="utf-8")
        after_csv = OUT_CSV.read_text(encoding="utf-8")
        if before is not None and (before != after or before_csv != after_csv):
            print("route_mount_inventory drift; rerun scripts/ci/route_mount_contract_guard.py")
            return 1
        print("route_mount_inventory_check_ok")
    else:
        print(f"route_mount_inventory_written entries={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
