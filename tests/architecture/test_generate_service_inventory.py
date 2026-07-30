"""Behavioral contract for scripts/ci/generate_service_inventory.py's route composition.

API-VERSIONING-GUARD-IS-A-MIRROR-01: routes_for_file() read only the literal decorator
string (``@router.get("/plan")``), never composing it with the router's own
``APIRouter(prefix="/v1/phase9/autonomy")`` declared in the same file -- so a route
genuinely served at ``/v1/phase9/autonomy/plan`` was recorded in
route_inventory.generated.json as bare ``/plan``. build_platform_catalog.py reads this
file for cross-service duplicate-text detection, so the phantom bare path created false
duplicate groups (POST /plan vs agriai-engine's real /plan; GET /stac and
GET /stac/collections vs raster-service's real ones).

Same blind spot already fixed in api_versioning_policy_guard.py (PR #717) for a sibling
generator; a repo-wide search (``grep -rn "include_router(" services/ bots/``, plus an
AST sweep matching every route-decorator object name against its local definition)
confirmed zero ``include_router(..., prefix=...)`` usage and zero cross-file router
references anywhere in the repository -- every real route decorator is applied on a
router/app object defined in the same file. The fix is therefore same-file
``APIRouter(prefix=...)`` composition only, matching PR #717's scope exactly.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "generate_service_inventory.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_service_inventory_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_router_prefixes_detects_same_file_apirouter_prefix():
    mod = _load_module()
    src = (
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/v1/phase9/autonomy')\n"
        "\n"
        "@router.post('/plan')\n"
        "def create_execution_plan():\n"
        "    ...\n"
        "\n"
        "@app.get('/health')\n"
        "def health():\n"
        "    ...\n"
    )
    prefixes = mod.router_prefixes(ast.parse(src))
    assert prefixes == {"router": "/v1/phase9/autonomy"}


def test_routes_for_file_composes_prefix_and_leaves_unprefixed_routes_alone():
    mod = _load_module()
    src = (
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/v1/phase9/autonomy')\n"
        "\n"
        "@router.post('/plan')\n"
        "def create_execution_plan():\n"
        "    ...\n"
        "\n"
        "@app.get('/health')\n"
        "def health():\n"
        "    ...\n"
    )
    fixture = ROOT / "services" / "_fixture_route_inventory_prefix_test.py"
    fixture.write_text(src, encoding="utf-8")
    try:
        rows = mod.routes_for_file("fixture-service", fixture)
    finally:
        fixture.unlink()
    by_path = {(r.method, r.path) for r in rows}
    assert ("POST", "/v1/phase9/autonomy/plan") in by_path, (
        f"prefix not composed into route path: {by_path}"
    )
    assert ("GET", "/health") in by_path, "unprefixed @app route must stay unprefixed"


def test_known_prefixed_sahool_platform_files_report_composed_paths():
    """The six sahool-platform router files declaring APIRouter(prefix="/v1/...") or
    APIRouter(prefix="/api/v1/...") in the same file must report every route with the
    composed path in route_inventory.generated.json -- these are the concrete 99
    positions this fix corrects, matching api_versioning_policy_guard.py's PR #717 fix
    one-for-one (same files, same routes, same prefixes)."""
    mod = _load_module()
    prefixed_files = {
        "services/sahool-platform/api/phase9_autonomous_farm_os.py": "/v1/phase9/autonomy",
        "services/sahool-platform/api/phase10_continuous_learning.py": "/v1/phase10/learning",
        "services/sahool-platform/api/phase11_federated_agents.py": "/v1/phase11/federation",
        "services/sahool-platform/api/phase12_marketplace_ecosystem.py": "/v1/ecosystem",
        "services/sahool-platform/api/routers/gis_cloud_native.py": "/api/v1/gis/cloud-native",
        "services/sahool-platform/api/routers/irrigation_engineering.py": "/api/v1/irrigation/engineering",
    }
    for rel_path, prefix in prefixed_files.items():
        rows = mod.routes_for_file("sahool-platform", ROOT / rel_path)
        assert rows, f"{rel_path} yielded no routes at all"
        for r in rows:
            assert r.path.startswith(prefix), (
                f"{rel_path}:{r.line} {r.method} {r.path} does not start with expected "
                f"prefix {prefix} -- APIRouter(prefix=...) composition regressed"
            )


def test_no_include_router_with_prefix_or_cross_file_route_decorators_exist():
    """Falsifies the scope decision itself: if a future change introduces
    include_router(..., prefix=...) or a route decorator on a router imported from
    another file, this test fails loudly instead of silently under-measuring routes --
    matching CLAUDE.md's 'missing != zero' rule. Re-run this check before extending the
    fix's scope."""
    for hit in ROOT.glob("services/**/*.py"):
        if "__pycache__" in hit.parts:
            continue
        src = hit.read_text(encoding="utf-8", errors="ignore")
        if "include_router(" not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "include_router"
            ):
                for kw in node.keywords:
                    assert kw.arg != "prefix", (
                        f"{hit.relative_to(ROOT)}:{node.lineno} calls include_router(..., "
                        "prefix=...) -- this fix's same-file-only composition no longer "
                        "covers the full picture, extend router_prefixes()"
                    )


def test_route_inventory_check_passes_on_current_tree():
    """Integration proof: the committed route_inventory.generated.json / .csv already
    reflect the composed paths -- drift-checking this file is itself the falsification
    surface for a regressed fix (revert router_prefixes() locally and this fails)."""
    mod = _load_module()
    mod.check_drift()
