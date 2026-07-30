from __future__ import annotations

import ast
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


def test_router_prefix_is_composed_with_route_path():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01: collect() read only the literal decorator
    string (``@router.get("/plan")``), never composing it with the router's own
    ``APIRouter(prefix="/v1/phase9/autonomy")`` declared in the same file -- so a route
    genuinely served at ``/v1/phase9/autonomy/plan`` was classified legacy_unversioned_business
    because its bare decorator text doesn't start with a version segment. A repo-wide search
    found no ``include_router(..., prefix=...)`` usage anywhere -- the only prefix mechanism
    actually used is same-file ``APIRouter(prefix=...)``, so the fix composes locally, with
    no cross-file router-mount tracing needed."""
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
    prefixes = guard._router_prefixes(ast.parse(src))
    assert prefixes == {"router": "/v1/phase9/autonomy"}

    # _routes() requires a real path under ROOT (_service_for does path.relative_to(ROOT)),
    # so exercise it against a throwaway fixture file rather than a bare AST.
    real_file = guard.ROOT / "services" / "_fixture_router_prefix_test.py"
    real_file.write_text(src, encoding="utf-8")
    try:
        rows = guard._routes(real_file)
    finally:
        real_file.unlink()
    by_path = {(r["method"], r["path"]) for r in rows}
    assert ("POST", "/v1/phase9/autonomy/plan") in by_path, (
        f"prefix not composed into route path: {by_path}"
    )
    assert ("GET", "/health") in by_path, "unprefixed @app route must stay unprefixed"
    composed = next(r for r in rows if r["path"] == "/v1/phase9/autonomy/plan")
    assert guard._classify(composed["path"]) == "versioned"


def test_known_prefixed_sahool_platform_routers_classify_as_versioned():
    """The six sahool-platform router files that declare APIRouter(prefix="/v1/...")
    or APIRouter(prefix="/api/v1/...") in the same file must have every one of their
    routes classified versioned once the prefix is composed -- these are the concrete
    99 positions this fix reclassifies, previously counted as legacy_unversioned_business
    purely because collect() couldn't see same-file router prefixes."""
    prefixed_files = (
        "services/sahool-platform/api/phase9_autonomous_farm_os.py",
        "services/sahool-platform/api/phase10_continuous_learning.py",
        "services/sahool-platform/api/phase11_federated_agents.py",
        "services/sahool-platform/api/phase12_marketplace_ecosystem.py",
        "services/sahool-platform/api/routers/gis_cloud_native.py",
        "services/sahool-platform/api/routers/irrigation_engineering.py",
    )
    rows = guard.collect()
    still_legacy = [
        r
        for r in rows
        if r["file"] in prefixed_files and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], (
        f"routes in prefix-declaring router files still misclassified: {still_legacy}"
    )


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


def test_guardrails_and_supervisor_agent_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, slice 2026-07-30 (agent B): both
    guardrails-engine/routers/validation.py and supervisor-agent/routers/agent.py
    declare their routers with no ``prefix=`` and are mounted flat
    (``register_routers`` docstrings in both files say so), so the decorator
    literal *is* the real runtime path -- unlike phase9-12/gis_cloud_native.py/
    irrigation_engineering.py, whose ``APIRouter(prefix=...)`` the classifier
    cannot see (documented in api_versioning_legacy_baseline.json). These eight
    routes were genuinely unversioned and are now migrated to /v1/*; none of
    them may remain in collect()'s legacy_unversioned_business output, and
    the old bare paths must not still be declared in either file.
    """
    rows = guard.collect()
    migrated_files = (
        "services/guardrails-engine/routers/validation.py",
        "services/supervisor-agent/routers/agent.py",
    )
    still_legacy = [
        r
        for r in rows
        if r["file"] in migrated_files and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "services/guardrails-engine/routers/validation.py": {
            "/validate",
            "/approve/{workflow_id}",
            "/workflow/{workflow_id}",
        },
        "services/supervisor-agent/routers/agent.py": {
            "/agent/query",
            "/agent/optimize",
            "/agent/tools",
            "/agent/journal/{invocation_id}",
            "/agent/actuator-audit",
        },
    }
    for f, old in old_paths.items():
        present = {r["path"] for r in rows if r["file"] == f}
        leaked_old = present & old
        assert not leaked_old, f"{f} still declares old path(s): {leaked_old}"


def test_edge_inference_and_knowledge_graph_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, Agent D slice 2 (2026-07-30): edge-inference's
    three routes (POST /inference/pest-detect, POST /inference/yield-estimate, POST
    /sync/trigger) and knowledge-graph's three routes (POST /nodes, POST /edges, GET
    /edges) declare their routers with no ``prefix=`` and are mounted flat (bare @app.*
    decorators), so the decorator literal is the real runtime path. All six moved to a
    leading /v1/ prefix. Falsified by construction: reverting any decorator to its old
    bare path makes this fail by naming the exact leaked path."""
    rows = guard.collect()
    migrated_files = (
        "services/edge-inference/main.py",
        "services/knowledge-graph/main.py",
    )
    still_legacy = [
        r
        for r in rows
        if r["file"] in migrated_files and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "services/edge-inference/main.py": {
            "/inference/pest-detect",
            "/inference/yield-estimate",
            "/sync/trigger",
        },
        "services/knowledge-graph/main.py": {"/nodes", "/edges"},
    }
    for f, old in old_paths.items():
        present = {r["path"] for r in rows if r["file"] == f}
        leaked_old = present & old
        assert not leaked_old, f"{f} still declares old path(s): {leaked_old}"

    new_paths = {
        "services/edge-inference/main.py": {
            ("POST", "/v1/inference/pest-detect"),
            ("POST", "/v1/inference/yield-estimate"),
            ("POST", "/v1/sync/trigger"),
        },
        "services/knowledge-graph/main.py": {
            ("POST", "/v1/nodes"),
            ("POST", "/v1/edges"),
            ("GET", "/v1/edges"),
        },
    }
    for f, expected in new_paths.items():
        present = {(r["method"], r["path"]) for r in rows if r["file"] == f}
        missing = expected - present
        assert not missing, f"{f} missing expected migrated route(s): {missing}"


def test_tts_service_and_local_ai_rag_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, Agent D slice 3 (2026-07-30): tts-service's
    router (services/tts-service/routers/tts.py) declares ``router = APIRouter()`` with
    no prefix, and local-ai-rag's routes are bare ``@app.*`` decorators -- in both cases
    the decorator literal is the real runtime path. All six moved to a leading /v1/
    prefix. local-ai-rag's POST /query and POST /ingest keep their bare-text siblings in
    the allowlist (ai_agronomist's own POST /query, rag-retrieval's own POST /ingest are
    untouched, out of this slice's scope) -- this test only asserts local-ai-rag's own
    file no longer declares the old bare paths, not that the shared text vanishes from
    the allowlist entirely. Falsified by construction: reverting any decorator to its
    old bare path makes this fail by naming the exact leaked path."""
    rows = guard.collect()
    migrated_files = (
        "services/tts-service/routers/tts.py",
        "services/local-ai-rag/main.py",
    )
    still_legacy = [
        r
        for r in rows
        if r["file"] in migrated_files and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "services/tts-service/routers/tts.py": {
            "/tts/voices",
            "/tts/status",
            "/tts/synthesize",
            "/tts/stream",
        },
        "services/local-ai-rag/main.py": {"/query", "/ingest"},
    }
    for f, old in old_paths.items():
        present = {r["path"] for r in rows if r["file"] == f}
        leaked_old = present & old
        assert not leaked_old, f"{f} still declares old path(s): {leaked_old}"

    new_paths = {
        "services/tts-service/routers/tts.py": {
            ("GET", "/v1/tts/voices"),
            ("GET", "/v1/tts/status"),
            ("POST", "/v1/tts/synthesize"),
            ("POST", "/v1/tts/stream"),
        },
        "services/local-ai-rag/main.py": {
            ("POST", "/v1/query"),
            ("POST", "/v1/ingest"),
        },
    }
    for f, expected in new_paths.items():
        present = {(r["method"], r["path"]) for r in rows if r["file"] == f}
        missing = expected - present
        assert not missing, f"{f} missing expected migrated route(s): {missing}"
