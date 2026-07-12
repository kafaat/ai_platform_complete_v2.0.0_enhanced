#!/usr/bin/env python3
"""Guard P1 main.py decomposition for platform, odoo-bridge, and vegetation.

This guard prevents regression after the conservative P1 refactors:
- sahool-platform/api/main.py must not re-own direct route decorators; platform
  health/internal routes live in routers/.
- odoo-bridge/main.py is a slim app/model shell; ERP sync/Odoo runtime lives in
  erp_runtime.py.
- vegetation-analysis-service/main.py is a slim app shell; vegetation runtime
  lives in vegetation_runtime.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _loc(rel: str) -> int:
    return len(_text(rel).splitlines())


def _route_decorators(rel: str) -> list[str]:
    tree = ast.parse(_text(rel), filename=rel)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr in ROUTE_METHODS
            ):
                route = (
                    dec.args[0].value
                    if dec.args and isinstance(dec.args[0], ast.Constant)
                    else "<dynamic>"
                )
                found.append(f"{dec.func.attr.upper()} {route} -> {node.name}")
    return found


def _function_names(rel: str) -> set[str]:
    tree = ast.parse(_text(rel), filename=rel)
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _assert_file(rel: str) -> None:
    if not (ROOT / rel).exists():
        raise SystemExit(f"missing expected P1 file: {rel}")


def main() -> int:
    # Platform residual bootstrap: routes moved out, registry remains.
    platform_main = "services/sahool-platform/api/main.py"
    for rel in [
        "services/sahool-platform/api/routers/platform_health.py",
        "services/sahool-platform/api/routers/internal_service.py",
    ]:
        _assert_file(rel)
    if _route_decorators(platform_main):
        raise SystemExit(
            f"platform main.py regained direct routes: {_route_decorators(platform_main)}"
        )
    if "register_routers(app)" not in _text(platform_main):
        raise SystemExit("platform main.py no longer delegates to router_registry")
    if _loc(platform_main) > 2550:
        raise SystemExit(f"platform main.py regression: LOC {_loc(platform_main)} > 2550")

    # Odoo bridge runtime extraction.
    odoo_main = "services/odoo-bridge/main.py"
    odoo_runtime = "services/odoo-bridge/erp_runtime.py"
    _assert_file(odoo_runtime)
    if _loc(odoo_main) > 250:
        raise SystemExit(f"odoo-bridge main.py regression: LOC {_loc(odoo_main)} > 250")
    heavy = {
        "sync_products",
        "sync_suppliers",
        "sync_warehouses",
        "sync_procurement_orders_to_odoo",
        "sync_purchase_order_inbound",
        "sync_field_costs_to_odoo",
        "periodic_sync",
    }
    if heavy & _function_names(odoo_main):
        raise SystemExit(
            f"odoo heavy sync functions returned to main.py: {sorted(heavy & _function_names(odoo_main))}"
        )
    if not heavy <= _function_names(odoo_runtime):
        raise SystemExit(
            f"odoo runtime missing heavy functions: {sorted(heavy - _function_names(odoo_runtime))}"
        )

    # Vegetation runtime extraction.
    veg_main = "services/vegetation-analysis-service/main.py"
    veg_runtime = "services/vegetation-analysis-service/vegetation_runtime.py"
    _assert_file(veg_runtime)
    if _loc(veg_main) > 180:
        raise SystemExit(f"vegetation main.py regression: LOC {_loc(veg_main)} > 180")
    veg_heavy = {
        "load_field",
        "run_analysis",
        # production-truth closure removed the synthetic _generate_timeseries entirely;
        # the authoritative reader took its place in the runtime module.
        "_current_ndvi_from_raster",
        "_current_ndvi_payload",
    }
    if veg_heavy & _function_names(veg_main):
        raise SystemExit(
            f"vegetation heavy functions returned to main.py: {sorted(veg_heavy & _function_names(veg_main))}"
        )
    if not veg_heavy <= _function_names(veg_runtime):
        raise SystemExit(
            f"vegetation runtime missing heavy functions: {sorted(veg_heavy - _function_names(veg_runtime))}"
        )
    # Three-container boundary (20260712): vegetation consumes a single validated
    # observation-bundle from raster-service and holds NO provider credentials/fetch.
    # Both direct-provider fetch functions must be absent from the whole service.
    banned = {"fetch_from_sentinel_hub", "fetch_from_cdse"}
    for path in (veg_main, veg_runtime):
        returned = banned & _function_names(path)
        if returned:
            raise SystemExit(
                f"vegetation direct provider fetch returned ({path}): {sorted(returned)} — RIV forbids it"
            )

    print("p1_main_decomposition_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
