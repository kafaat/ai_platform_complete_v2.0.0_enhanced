from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
import api_versioning_policy_guard as guard  # noqa: E402

pytestmark = pytest.mark.unit


def test_api_versioning_policy_guard_inventory_is_current():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "scripts/ci/api_versioning_policy_guard.py", "--check"],
        cwd=root,
        check=True,
    )


def test_is_test_file_excludes_by_directory_and_filename():
    root = guard.ROOT
    assert guard._is_test_file(
        root / "services/sahool-platform/tests/test_correlation_middleware.py"
    )
    assert guard._is_test_file(root / "services/soil-service/tests/conftest.py")
    assert guard._is_test_file(root / "services/actuator-service/test_commands.py")
    assert not guard._is_test_file(root / "services/soil-service/main.py")
    assert not guard._is_test_file(root / "services/soil-service/routers/readings.py")


def test_collect_excludes_test_file_routes_structurally():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01 false positive: GET /probe inside
    test_correlation_middleware.py is a test fixture, not a production route."""
    rows = guard.collect()
    test_file_rows = [r for r in rows if guard._is_test_file(guard.ROOT / r["file"])]
    assert test_file_rows == [], f"routes leaked from test files: {test_file_rows}"


def test_runtime_identity_is_infra_not_legacy_business():
    """GET /runtime-identity is grouped with healthz/readyz/metrics as a
    provenance/infrastructure route (CLAUDE.md; platform_route_ownership_guard
    already classifies it this way) and is contract-declared, probe-configured,
    and attestation-tested -- not a genuine unversioned business route."""
    assert guard._classify("/runtime-identity") == "infra"
    rows = guard.collect()
    leaked = [
        r for r in rows if r["path"] == "/runtime-identity" and r["classification"] != "infra"
    ]
    assert leaked == [], f"/runtime-identity leaked into a non-infra classification: {leaked}"


def test_mcp_protocol_atomic_contract_migrated_to_versioned_prefix():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, Agent A slice 1 (2026-07-30): the MCP
    protocol surface (``GET /mcp/v1/tools`` across generic_context_server.py,
    sentinel_hub_server.py, weather_server.py, wofost_server.py; ``POST
    /mcp/v1/tools/call`` across those four plus market_server.py; ``GET
    /mcp/v1/tools/list`` in market_server.py alone) moved to a leading version
    prefix (``/v1/mcp/tools``, ``/v1/mcp/tools/call``, ``/v1/mcp/tools/list``) so
    the classifier's ``^(?:/api)?/v[0-9]+`` prefix rule recognizes it as versioned.
    Falsified by construction: re-introducing the pre-migration ``/mcp/v1/...``
    path on any decorator makes this fail by naming the exact leaked path."""
    rows = guard.collect()
    mcp_server_rows = [r for r in rows if r["service"] == "mcp_servers"]

    old_prefix_leaks = [r for r in mcp_server_rows if r["path"].startswith("/mcp/v1/tools")]
    assert old_prefix_leaks == [], (
        f"pre-migration /mcp/v1/tools* path still present: {old_prefix_leaks}"
    )

    new_paths = {(r["method"], r["path"]) for r in mcp_server_rows}
    for expected in (
        ("GET", "/v1/mcp/tools"),
        ("POST", "/v1/mcp/tools/call"),
        ("GET", "/v1/mcp/tools/list"),
    ):
        assert expected in new_paths, f"expected migrated route {expected} not found in inventory"

    for r in mcp_server_rows:
        if r["path"].startswith("/v1/mcp/tools"):
            assert r["classification"] == "versioned", (
                f"{r['method']} {r['path']} ({r['file']}:{r['line']}) did not classify as "
                f"versioned: {r['classification']}"
            )


def test_products_cross_service_contract_migrated_to_versioned_prefix():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, Agent A slice 2 (2026-07-30): ``GET
    /products`` collapsed two unrelated routes in two different services --
    services/mcp_servers/market_server.py (MCP marketplace products, port 8094)
    and services/odoo-bridge/routers/catalog.py (ERP products via Odoo, port
    8126) -- into a single (method, path) string in the legacy allowlist. Both
    moved together to ``GET /v1/products`` in the same slice/PR since the guard
    dedups by (method, path) text, not by service. Falsified by construction:
    reverting either decorator to ``/products`` makes this fail by naming the
    exact service + file:line that leaked."""
    rows = guard.collect()
    old_path_leaks = [r for r in rows if r["path"] == "/products"]
    assert old_path_leaks == [], f"pre-migration /products path still present: {old_path_leaks}"

    new_rows = [r for r in rows if r["method"] == "GET" and r["path"] == "/v1/products"]
    services_seen = {r["service"] for r in new_rows}
    assert services_seen == {"mcp_servers", "odoo-bridge"}, (
        f"expected GET /v1/products in both mcp_servers and odoo-bridge, found: {services_seen}"
    )
    for r in new_rows:
        assert r["classification"] == "versioned", (
            f"{r['method']} {r['path']} ({r['file']}:{r['line']}) did not classify as "
            f"versioned: {r['classification']}"
        )


def test_actuator_commands_migrated_to_versioned_prefix():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, Agent A slice 3 (2026-07-30): the
    actuator-service command-dispatch surface -- ``POST /command`` and ``GET
    /commands`` (services/actuator-service/routers/commands.py), plus ``GET
    /idempotency/metrics`` (services/actuator-service/routers/metrics.py) --
    moved to ``/v1/command``, ``/v1/commands``, ``/v1/idempotency/metrics``.
    Elevated-caution domain (safety-critical physical device dispatch):
    verified zero external callers before migrating -- repo-wide grep found no
    frontend/mobile/nginx/docker-compose reference to any of the three old
    paths, only this service's own tests. Falsified by construction: reverting
    any of the three decorators makes this fail by naming the exact leaked
    path."""
    rows = guard.collect()
    actuator_rows = [r for r in rows if r["service"] == "actuator-service"]

    old_path_leaks = [
        r for r in actuator_rows if r["path"] in {"/command", "/commands", "/idempotency/metrics"}
    ]
    assert old_path_leaks == [], f"pre-migration actuator path still present: {old_path_leaks}"

    new_paths = {(r["method"], r["path"]) for r in actuator_rows}
    for expected in (
        ("POST", "/v1/command"),
        ("GET", "/v1/commands"),
        ("GET", "/v1/idempotency/metrics"),
    ):
        assert expected in new_paths, f"expected migrated route {expected} not found in inventory"

    for r in actuator_rows:
        if r["path"].startswith("/v1/command") or r["path"] == "/v1/idempotency/metrics":
            assert r["classification"] == "versioned", (
                f"{r['method']} {r['path']} ({r['file']}:{r['line']}) did not classify as "
                f"versioned: {r['classification']}"
            )
