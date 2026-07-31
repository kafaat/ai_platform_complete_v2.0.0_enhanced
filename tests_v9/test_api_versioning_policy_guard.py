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


def test_baseline_check_rejects_legacy_route_swap_not_just_count():
    """The ratchet in --check enforced only len(current) <= ceiling (a bare count),
    not that the *same* set is shrinking — closing 2 routes and opening 2 different
    ones would pass silently as long as the total stayed <= ceiling. Fixed by adding
    a frozen `routes` set to api_versioning_legacy_baseline.json and a second,
    independent condition: current_legacy_set must be a subset of the frozen set.

    Falsified by construction: temporarily drop one entry from the frozen `routes`
    list (simulating a debt-swap where the live set still contains a route the
    baseline no longer covers) and confirm --check fails naming that exact route,
    then restore and confirm --check passes again."""
    import json

    root = Path(__file__).resolve().parents[1]
    baseline_path = root / "docs" / "architecture" / "api_versioning_legacy_baseline.json"
    original = baseline_path.read_text(encoding="utf-8")
    data = json.loads(original)
    assert data.get("routes"), "baseline must declare a frozen `routes` set for this guard to work"
    dropped = data["routes"][0]

    try:
        tampered = dict(data)
        tampered["routes"] = [r for r in data["routes"] if r != dropped]
        baseline_path.write_text(
            json.dumps(tampered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        result = subprocess.run(
            [sys.executable, "scripts/ci/api_versioning_policy_guard.py", "--check"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, "swapping one frozen route out must fail --check"
        assert dropped in result.stdout + result.stderr, (
            f"failure must name the escaped route {dropped!r} explicitly"
        )
    finally:
        baseline_path.write_text(original, encoding="utf-8")

    restored = subprocess.run(
        [sys.executable, "scripts/ci/api_versioning_policy_guard.py", "--check"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert restored.returncode == 0, f"restoring the baseline must pass --check: {restored.stdout}"


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


def test_ai_agronomist_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, Agent D slice 4 (2026-07-30):
    services/ai_agronomist/main.py declares all nine routes as bare ``@app.*``
    decorators with no router prefix, so the decorator literal is the real runtime
    path. All nine moved to a leading /v1/ prefix. POST /recommend's bare text was
    shared with agriai-engine/main.py:237 (untouched, next slice), so it survives in
    the allowlist under its bare text with one remaining member; POST /v1/query
    coincidentally collides with local-ai-rag's own POST /v1/query (both moved
    independently in sibling slices) -- a new duplicate-text governance decision was
    added in config/platform_catalog_overrides.yml for that pairing. Falsified by
    construction: reverting any decorator to its old bare path makes this fail by
    naming the exact leaked path."""
    rows = guard.collect()
    still_legacy = [
        r
        for r in rows
        if r["file"] == "services/ai_agronomist/main.py"
        and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "/approvals/pending",
        "/approvals/approve",
        "/approvals/deny",
        "/approvals/resume",
        "/prescription/export-preview",
        "/query",
        "/chat",
        "/explain",
        "/recommend",
    }
    present = {r["path"] for r in rows if r["file"] == "services/ai_agronomist/main.py"}
    leaked_old = present & old_paths
    assert not leaked_old, f"ai_agronomist still declares old path(s): {leaked_old}"

    expected = {
        ("GET", "/v1/approvals/pending"),
        ("POST", "/v1/approvals/approve"),
        ("POST", "/v1/approvals/deny"),
        ("POST", "/v1/approvals/resume"),
        ("POST", "/v1/prescription/export-preview"),
        ("POST", "/v1/query"),
        ("POST", "/v1/chat"),
        ("POST", "/v1/explain"),
        ("POST", "/v1/recommend"),
    }
    present_pairs = {
        (r["method"], r["path"]) for r in rows if r["file"] == "services/ai_agronomist/main.py"
    }
    missing = expected - present_pairs
    assert not missing, f"ai_agronomist missing expected migrated route(s): {missing}"


def test_rag_retrieval_and_agriai_engine_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, Agent D slice 5 (2026-07-30): both
    services declare bare ``@app.*`` decorators with no router prefix, so the
    decorator literal is the real runtime path. rag-retrieval's two routes and
    agriai-engine's four routes all moved to /v1/*. Two accidental collisions
    surfaced after independent migrations: POST /v1/ingest (rag-retrieval vs
    local-ai-rag, slice 3) and POST /v1/recommend (agriai-engine vs ai_agronomist,
    slice 4) -- both documented with new service_scoped_semantics governance
    decisions in config/platform_catalog_overrides.yml. Falsified by construction:
    reverting any decorator to its old bare path makes this fail by naming the
    exact leaked path."""
    rows = guard.collect()
    migrated_files = (
        "services/rag-retrieval/main.py",
        "services/agriai-engine/main.py",
    )
    still_legacy = [
        r
        for r in rows
        if r["file"] in migrated_files and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "services/rag-retrieval/main.py": {"/ingest", "/search"},
        "services/agriai-engine/main.py": {"/recommend", "/simulate", "/plan", "/replay/verify"},
    }
    for f, old in old_paths.items():
        present = {r["path"] for r in rows if r["file"] == f}
        leaked_old = present & old
        assert not leaked_old, f"{f} still declares old path(s): {leaked_old}"

    new_paths = {
        "services/rag-retrieval/main.py": {
            ("POST", "/v1/ingest"),
            ("POST", "/v1/search"),
        },
        "services/agriai-engine/main.py": {
            ("POST", "/v1/recommend"),
            ("POST", "/v1/simulate"),
            ("POST", "/v1/plan"),
            ("POST", "/v1/replay/verify"),
        },
    }
    for f, expected in new_paths.items():
        present = {(r["method"], r["path"]) for r in rows if r["file"] == f}
        missing = expected - present
        assert not missing, f"{f} missing expected migrated route(s): {missing}"


def test_raster_service_pr_r2_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, raster-service PR-R2 (2026-07-31): the
    internal/operational routes in routers/jobs.py and routers/storage.py (registered
    via register_routers()'s flat, prefix-less inclusion, so the decorator literal is
    the real runtime path) moved to /v1/*. All 8 are require_service_token, no browser
    exposure. The one real internal consumer,
    services/sahool-platform/api/raster_service_client.py's get_job_result(), was
    updated in the same commit to call /v1/jobs/{job_id}/result -- see
    docs/architecture/raster_service_route_migration_plan.md. Falsified by
    construction: reverting any decorator to its old bare path makes this fail by
    naming the exact leaked path."""
    rows = guard.collect()
    migrated_files = (
        "services/raster-service/routers/jobs.py",
        "services/raster-service/routers/storage.py",
    )
    still_legacy = [
        r
        for r in rows
        if r["file"] in migrated_files and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "services/raster-service/routers/jobs.py": {"/jobs/{job_id}", "/jobs/{job_id}/result"},
        "services/raster-service/routers/storage.py": {
            "/upload/raster",
            "/upload/drone",
            "/storage/stats",
            "/storage/cleanup",
            "/offline/packs",
            "/offline/packs/{pack_name}",
        },
    }
    for f, old in old_paths.items():
        present = {r["path"] for r in rows if r["file"] == f}
        leaked_old = present & old
        assert not leaked_old, f"{f} still declares old path(s): {leaked_old}"

    new_paths = {
        "services/raster-service/routers/jobs.py": {
            ("GET", "/v1/jobs/{job_id}"),
            ("GET", "/v1/jobs/{job_id}/result"),
        },
        "services/raster-service/routers/storage.py": {
            ("POST", "/v1/upload/raster"),
            ("POST", "/v1/upload/drone"),
            ("GET", "/v1/storage/stats"),
            ("POST", "/v1/storage/cleanup"),
            ("GET", "/v1/offline/packs"),
            ("GET", "/v1/offline/packs/{pack_name}"),
        },
    }
    for f, expected in new_paths.items():
        present = {(r["method"], r["path"]) for r in rows if r["file"] == f}
        missing = expected - present
        assert not missing, f"{f} missing expected migrated route(s): {missing}"

    client = (
        guard.ROOT / "services" / "sahool-platform" / "api" / "raster_service_client.py"
    ).read_text(encoding="utf-8")
    assert 'f"/v1/jobs/{job_id}/result"' in client
    assert 'f"/jobs/{job_id}/result"' not in client


def test_raster_service_pr_r3_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, raster-service PR-R3 (2026-07-31): the
    imagery/catalog/process routes in routers/analysis.py, routers/fields.py (one
    route), routers/observability.py, routers/processing.py, routers/stac.py, and
    routers/timeseries_routes.py (all flat, prefix-less inclusion, so the decorator
    literal is the real runtime path) moved to /v1/*. All are require_service_token
    except the three STAC routes and the bare GET /imagery/timeseries, which are
    PUBLIC_CATALOG (bbox-scoped public search/catalog, no tenant data). The two real
    internal consumers,
    services/sahool-platform/api/raster_service_client.py's get_indices_sync() and
    process_indicator_batch(), were updated in the same commit to call
    /v1/indices and /v1/process/batch -- see
    docs/architecture/raster_service_route_migration_plan.md. Falsified by
    construction: reverting any decorator to its old bare path makes this fail by
    naming the exact leaked path."""
    rows = guard.collect()
    migrated_files = (
        "services/raster-service/routers/analysis.py",
        "services/raster-service/routers/fields.py",
        "services/raster-service/routers/observability.py",
        "services/raster-service/routers/processing.py",
        "services/raster-service/routers/stac.py",
        "services/raster-service/routers/timeseries_routes.py",
    )
    still_legacy = [
        r
        for r in rows
        if r["file"] in migrated_files and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "services/raster-service/routers/analysis.py": {
            "/zones/classify",
            "/change/detect",
            "/fvc/compute",
            "/sar/rvi",
            "/terrain/slope",
            "/cog/validate",
            "/salinity/classify",
            "/salinity/calibrate",
        },
        "services/raster-service/routers/observability.py": {"/info/{layer_id}", "/indices"},
        "services/raster-service/routers/processing.py": {
            "/process",
            "/raw/process",
            "/process/batch",
        },
        "services/raster-service/routers/stac.py": {
            "/stac",
            "/stac/collections",
            "/stac/mosaicjson",
        },
        "services/raster-service/routers/timeseries_routes.py": {
            "/imagery/timeseries",
            "/imagery/timeseries/analyze",
            "/imagery/timeseries/parallel",
        },
    }
    for f, old in old_paths.items():
        present = {r["path"] for r in rows if r["file"] == f}
        leaked_old = present & old
        assert not leaked_old, f"{f} still declares old path(s): {leaked_old}"
    fields_present = {
        r["path"] for r in rows if r["file"] == "services/raster-service/routers/fields.py"
    }
    assert "/gis/admin-boundaries" not in fields_present, (
        "fields.py still declares old /gis/admin-boundaries"
    )

    new_paths = {
        "services/raster-service/routers/analysis.py": {
            ("POST", "/v1/zones/classify"),
            ("POST", "/v1/change/detect"),
            ("POST", "/v1/fvc/compute"),
            ("POST", "/v1/sar/rvi"),
            ("POST", "/v1/terrain/slope"),
            ("GET", "/v1/cog/validate"),
            ("POST", "/v1/salinity/classify"),
            ("POST", "/v1/salinity/calibrate"),
        },
        "services/raster-service/routers/observability.py": {
            ("GET", "/v1/info/{layer_id}"),
            ("GET", "/v1/indices"),
        },
        "services/raster-service/routers/processing.py": {
            ("POST", "/v1/process"),
            ("POST", "/v1/raw/process"),
            ("POST", "/v1/process/batch"),
        },
        "services/raster-service/routers/stac.py": {
            ("GET", "/v1/stac"),
            ("GET", "/v1/stac/collections"),
            ("POST", "/v1/stac/mosaicjson"),
        },
        "services/raster-service/routers/timeseries_routes.py": {
            ("GET", "/v1/imagery/timeseries"),
            ("POST", "/v1/imagery/timeseries/analyze"),
            ("POST", "/v1/imagery/timeseries/parallel"),
        },
    }
    for f, expected in new_paths.items():
        present = {(r["method"], r["path"]) for r in rows if r["file"] == f}
        missing = expected - present
        assert not missing, f"{f} missing expected migrated route(s): {missing}"
    assert ("GET", "/v1/gis/admin-boundaries") in {
        (r["method"], r["path"])
        for r in rows
        if r["file"] == "services/raster-service/routers/fields.py"
    }, "fields.py missing expected migrated route /v1/gis/admin-boundaries"

    client = (
        guard.ROOT / "services" / "sahool-platform" / "api" / "raster_service_client.py"
    ).read_text(encoding="utf-8")
    assert '"/v1/indices"' in client
    assert '"/indices"' not in client
    assert '"/v1/process/batch"' in client
    assert '"/process/batch"' not in client


def test_raster_service_pr_r4_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, raster-service PR-R4 (2026-07-31): the
    tile/rendering routes in routers/tiles.py (flat, prefix-less inclusion, so the
    decorator literal is the real runtime path) moved to /v1/*. Both are
    layer_scoped (require_layer_tenant + require_layer_tenant_authorized), no
    browser-facing prefix distinction from the rest of the service. PR-R1's
    exhaustive repo-wide search found zero live external or internal
    service-to-service consumers for either route -- migration is confined to the
    two decorators plus the embedded self-referential fallback tiles URL in the
    same file -- see docs/architecture/raster_service_route_migration_plan.md.
    This closes the raster-service migration: all 30 originally-classified routes
    are now versioned. Falsified by construction: reverting either decorator to its
    old bare path makes this fail by naming the exact leaked path."""
    rows = guard.collect()
    migrated_files = ("services/raster-service/routers/tiles.py",)
    still_legacy = [
        r
        for r in rows
        if r["file"] in migrated_files and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "services/raster-service/routers/tiles.py": {
            "/tiles/{layer_id}/{z}/{x}/{y}.png",
            "/layers/{layer_id}/tilejson",
        },
    }
    for f, old in old_paths.items():
        present = {r["path"] for r in rows if r["file"] == f}
        leaked_old = present & old
        assert not leaked_old, f"{f} still declares old path(s): {leaked_old}"

    new_paths = {
        "services/raster-service/routers/tiles.py": {
            ("GET", "/v1/tiles/{layer_id}/{z}/{x}/{y}.png"),
            ("GET", "/v1/layers/{layer_id}/tilejson"),
        },
    }
    for f, expected in new_paths.items():
        present = {(r["method"], r["path"]) for r in rows if r["file"] == f}
        missing = expected - present
        assert not missing, f"{f} missing expected migrated route(s): {missing}"

    tiles = (guard.ROOT / "services" / "raster-service" / "routers" / "tiles.py").read_text(
        encoding="utf-8"
    )
    assert 'f"/v1/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png"' in tiles
    assert 'f"/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png"' not in tiles

    raster_service_routes = {
        (r["method"], r["path"])
        for r in rows
        if r["service"] == "raster-service" and r["classification"] == "legacy_unversioned_business"
    }
    assert raster_service_routes == set(), (
        f"raster-service migration incomplete after PR-R4: {sorted(raster_service_routes)}"
    )


def test_soil_service_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, soil-service (2026-07-31): the 5
    remaining unversioned routes in routers/modbus.py, routers/readings.py, and
    routers/soil_profile.py (flat, prefix-less inclusion, so the decorator literal
    is the real runtime path) moved to /v1/soil/*. All are require_service_token
    (no PUBLIC_CATALOG/layer/field-scoped taxonomy exists for soil-service). The
    one real internal consumer,
    services/sahool-platform/core/field_intelligence_adapters.py's
    fetch_soil_baseline(), was updated in the same commit to call
    /v1/soil/soilgrids. Falsified by construction: reverting any decorator to its
    old bare path makes this fail by naming the exact leaked path."""
    rows = guard.collect()
    migrated_files = (
        "services/soil-service/routers/modbus.py",
        "services/soil-service/routers/readings.py",
        "services/soil-service/routers/soil_profile.py",
    )
    still_legacy = [
        r
        for r in rows
        if r["file"] in migrated_files and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "services/soil-service/routers/modbus.py": {"/soil/decode/modbus"},
        "services/soil-service/routers/readings.py": {
            "/soil/readings/{field_id}",
            "/soil/ingest",
        },
        "services/soil-service/routers/soil_profile.py": {"/soil/suitability", "/soil/soilgrids"},
    }
    for f, old in old_paths.items():
        present = {r["path"] for r in rows if r["file"] == f}
        leaked_old = present & old
        assert not leaked_old, f"{f} still declares old path(s): {leaked_old}"

    new_paths = {
        "services/soil-service/routers/modbus.py": {("POST", "/v1/soil/decode/modbus")},
        "services/soil-service/routers/readings.py": {
            ("GET", "/v1/soil/readings/{field_id}"),
            ("POST", "/v1/soil/ingest"),
        },
        "services/soil-service/routers/soil_profile.py": {
            ("POST", "/v1/soil/suitability"),
            ("GET", "/v1/soil/soilgrids"),
        },
    }
    for f, expected in new_paths.items():
        present = {(r["method"], r["path"]) for r in rows if r["file"] == f}
        missing = expected - present
        assert not missing, f"{f} missing expected migrated route(s): {missing}"

    adapters = (
        guard.ROOT / "services" / "sahool-platform" / "core" / "field_intelligence_adapters.py"
    ).read_text(encoding="utf-8")
    assert 'f"{SOIL_URL}/v1/soil/soilgrids"' in adapters
    assert 'f"{SOIL_URL}/soil/soilgrids"' not in adapters

    soil_service_routes = {
        (r["method"], r["path"])
        for r in rows
        if r["service"] == "soil-service" and r["classification"] == "legacy_unversioned_business"
    }
    assert soil_service_routes == set(), (
        f"soil-service migration incomplete: {sorted(soil_service_routes)}"
    )


def test_mcp_servers_market_rest_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, mcp_servers (2026-07-31): the 7
    remaining unversioned REST routes in market_server.py (flat @app.<method>
    decorators, no APIRouter/prefix -- same registration pattern as the
    already-versioned GET /v1/products in the same file) moved to /v1/*. All
    use Depends(_get_current_user) (Bearer/JWT, browser-facing) unlike the
    service-token routes migrated in other services. Zero real code consumers
    found by repo-wide search (frontend/mobile/nginx/supervisor-agent/
    odoo-bridge) -- the nginx.fixed.conf/nginx.unified.conf /api/market/
    gateway is a transparent proxy (no rewrite), so no upstream config change
    is needed either. Falsified by construction: reverting any decorator to
    its old bare path makes this fail by naming the exact leaked path."""
    rows = guard.collect()
    migrated_file = "services/mcp_servers/market_server.py"
    still_legacy = [
        r
        for r in rows
        if r["file"] == migrated_file and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "/suppliers/{supplier_id}",
        "/procurement",
        "/procurement/{order_id}",
        "/sales",
        "/price-history/{category}",
        "/analytics/{tenant_id}",
    }
    present = {r["path"] for r in rows if r["file"] == migrated_file}
    leaked_old = present & old_paths
    assert not leaked_old, f"{migrated_file} still declares old path(s): {leaked_old}"

    new_paths = {
        ("GET", "/v1/suppliers/{supplier_id}"),
        ("POST", "/v1/procurement"),
        ("GET", "/v1/procurement/{order_id}"),
        ("POST", "/v1/sales"),
        ("GET", "/v1/sales"),
        ("GET", "/v1/price-history/{category}"),
        ("GET", "/v1/analytics/{tenant_id}"),
    }
    present_pairs = {(r["method"], r["path"]) for r in rows if r["file"] == migrated_file}
    missing = new_paths - present_pairs
    assert not missing, f"{migrated_file} missing expected migrated route(s): {missing}"

    mcp_servers_legacy = {
        (r["method"], r["path"])
        for r in rows
        if r["service"] == "mcp_servers" and r["classification"] == "legacy_unversioned_business"
    }
    assert mcp_servers_legacy == set(), (
        f"mcp_servers still has legacy_unversioned_business routes: {sorted(mcp_servers_legacy)}"
    )


def test_odoo_bridge_erp_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, odoo-bridge/erp-bridge (2026-07-31,
    seventh and final active migration slice): the 7 remaining unversioned
    routes across routers/catalog.py (4), routers/health.py (1,
    /readyz/capabilities -- reports ERP capability state as data, not a
    container-health judgment, so it doesn't qualify for the infra allowlist
    the way /healthz/readyz do), routers/sync.py (1), and routers/webhooks.py
    (1, POST /webhook/odoo -- called by an external Odoo instance, not code in
    this repo) moved to /v1/*. All use main.require_auth (Bearer/JWT) except
    the webhook, which uses a shared X-Webhook-Secret header. Falsified by
    construction: reverting any decorator to its old bare path makes this fail
    by naming the exact leaked path."""
    rows = guard.collect()
    migrated_files = (
        "services/odoo-bridge/routers/catalog.py",
        "services/odoo-bridge/routers/health.py",
        "services/odoo-bridge/routers/sync.py",
        "services/odoo-bridge/routers/webhooks.py",
    )
    still_legacy = [
        r
        for r in rows
        if r["file"] in migrated_files and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "services/odoo-bridge/routers/catalog.py": {
            "/erp/provider",
            "/config",
            "/logs",
            "/suppliers",
        },
        "services/odoo-bridge/routers/health.py": {"/readyz/capabilities"},
        "services/odoo-bridge/routers/sync.py": {"/sync"},
        "services/odoo-bridge/routers/webhooks.py": {"/webhook/odoo"},
    }
    for f, old in old_paths.items():
        present = {r["path"] for r in rows if r["file"] == f}
        leaked_old = present & old
        assert not leaked_old, f"{f} still declares old path(s): {leaked_old}"

    new_paths = {
        "services/odoo-bridge/routers/catalog.py": {
            ("GET", "/v1/erp/provider"),
            ("GET", "/v1/config"),
            ("GET", "/v1/logs"),
            ("GET", "/v1/suppliers"),
        },
        "services/odoo-bridge/routers/health.py": {("GET", "/v1/readyz/capabilities")},
        "services/odoo-bridge/routers/sync.py": {("POST", "/v1/sync")},
        "services/odoo-bridge/routers/webhooks.py": {("POST", "/v1/webhook/odoo")},
    }
    for f, expected in new_paths.items():
        present = {(r["method"], r["path"]) for r in rows if r["file"] == f}
        missing = expected - present
        assert not missing, f"{f} missing expected migrated route(s): {missing}"

    sync_src = (guard.ROOT / "services" / "odoo-bridge" / "routers" / "sync.py").read_text(
        encoding="utf-8"
    )
    assert "Check /v1/readyz/capabilities for capability status." in sync_src
    assert "Check /readyz/capabilities for capability status." not in sync_src

    odoo_bridge_legacy = {
        (r["method"], r["path"])
        for r in rows
        if r["service"] == "odoo-bridge" and r["classification"] == "legacy_unversioned_business"
    }
    assert odoo_bridge_legacy == set(), (
        f"odoo-bridge still has legacy_unversioned_business routes: {sorted(odoo_bridge_legacy)}"
    )


def test_video_processor_stream_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, video-processor (2026-07-31, a
    newly-discovered slice surfaced only during erp-bridge's final
    remeasurement, not part of the originally-announced sequence): the 8
    unversioned routes in routers/streams.py (flat, prefix-less inclusion, so
    the decorator literal is the real runtime path) moved to /v1/streams*.
    All use main._get_current_user (Bearer/JWT). Zero real consumers found by
    repo-wide search: frontend/mobile have zero literal references; the live
    nginx.v9.conf /api/video/ gateway is a transparent proxy (no rewrite)
    restricted to private network ranges only (no browser-facing exposure);
    no other service defines a URL constant pointing at video-processor.
    Falsified by construction: reverting any decorator to its old bare path
    makes this fail by naming the exact leaked path."""
    rows = guard.collect()
    migrated_file = "services/video-processor/routers/streams.py"
    still_legacy = [
        r
        for r in rows
        if r["file"] == migrated_file and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "/streams",
        "/streams/{stream_id}",
        "/streams/{stream_id}/snapshot",
        "/streams/{stream_id}/record/start",
        "/streams/{stream_id}/record/stop",
    }
    present = {r["path"] for r in rows if r["file"] == migrated_file}
    leaked_old = present & old_paths
    assert not leaked_old, f"{migrated_file} still declares old path(s): {leaked_old}"

    new_paths = {
        ("POST", "/v1/streams"),
        ("DELETE", "/v1/streams/{stream_id}"),
        ("GET", "/v1/streams/{stream_id}"),
        ("GET", "/v1/streams"),
        ("POST", "/v1/streams/{stream_id}/snapshot"),
        ("GET", "/v1/streams/{stream_id}/snapshot"),
        ("POST", "/v1/streams/{stream_id}/record/start"),
        ("POST", "/v1/streams/{stream_id}/record/stop"),
    }
    present_pairs = {(r["method"], r["path"]) for r in rows if r["file"] == migrated_file}
    missing = new_paths - present_pairs
    assert not missing, f"{migrated_file} missing expected migrated route(s): {missing}"

    video_processor_legacy = {
        (r["method"], r["path"])
        for r in rows
        if r["service"] == "video-processor"
        and r["classification"] == "legacy_unversioned_business"
    }
    assert video_processor_legacy == set(), (
        f"video-processor still has legacy_unversioned_business routes: "
        f"{sorted(video_processor_legacy)}"
    )


def test_auth_service_routes_are_versioned():
    """API-VERSIONING-GUARD-IS-A-MIRROR-01, services/auth (2026-07-31, the
    final and highest-risk slice: 24 routes gating platform-wide login/
    session/authorization). Flat, prefix-less router registration across 9
    files (email_verify.py, invitations.py, mfa.py, password_reset.py,
    registration.py, season_edge_sign.py, session.py, tenants.py, users.py)
    moved bare /auth/* decorators to /v1/auth/*. Two of the 24 are nginx
    internal auth_request subrequest targets (_auth_verify -> GET
    /v1/auth/verify, _auth_edge_sign -> GET /v1/auth/edge-sign) whose
    proxy_pass targets were updated in lockstep across nginx.v9.conf,
    nginx.fixed.conf, nginx.unified.conf, nginx.light.conf and
    frontend/nginx.conf; the client-facing /auth/* location blocks in all
    five configs now rewrite both the frontend's double-prefixed
    (/auth/auth/x) and a direct client's single-prefixed (/auth/x)
    convention to /v1/auth/x, so frontend/src/services/api/auth.ts and the
    mobile app's api_service.dart needed zero code changes. Falsified by
    construction: reverting any decorator to its old bare path makes this
    fail by naming the exact leaked path."""
    rows = guard.collect()
    auth_files = {
        "services/auth/routers/email_verify.py",
        "services/auth/routers/invitations.py",
        "services/auth/routers/mfa.py",
        "services/auth/routers/password_reset.py",
        "services/auth/routers/registration.py",
        "services/auth/routers/season_edge_sign.py",
        "services/auth/routers/session.py",
        "services/auth/routers/tenants.py",
        "services/auth/routers/users.py",
    }
    still_legacy = [
        r
        for r in rows
        if r["file"] in auth_files and r["classification"] == "legacy_unversioned_business"
    ]
    assert still_legacy == [], f"routes still unversioned after migration: {still_legacy}"

    old_paths = {
        "/auth/verify",
        "/auth/verify/confirm",
        "/auth/verify/request",
        "/auth/verify/status",
        "/auth/invitations",
        "/auth/invitations/accept",
        "/auth/invitations/{invitation_id}",
        "/auth/mfa/activate",
        "/auth/mfa/disable",
        "/auth/mfa/setup",
        "/auth/password-reset/confirm",
        "/auth/password-reset/request",
        "/auth/change-password",
        "/auth/register",
        "/auth/edge-sign",
        "/auth/login",
        "/auth/logout",
        "/auth/me",
        "/auth/refresh",
        "/auth/tenants",
        "/auth/users",
        "/auth/users/{user_id}/deactivate",
        "/auth/users/{user_id}/role",
    }
    present = {r["path"] for r in rows if r["file"] in auth_files}
    leaked_old = present & old_paths
    assert not leaked_old, f"auth routers still declare old path(s): {leaked_old}"

    new_paths = {
        ("GET", "/v1/auth/verify"),
        ("POST", "/v1/auth/verify/confirm"),
        ("POST", "/v1/auth/verify/request"),
        ("GET", "/v1/auth/verify/status"),
        ("POST", "/v1/auth/invitations"),
        ("GET", "/v1/auth/invitations"),
        ("POST", "/v1/auth/invitations/accept"),
        ("DELETE", "/v1/auth/invitations/{invitation_id}"),
        ("POST", "/v1/auth/mfa/activate"),
        ("POST", "/v1/auth/mfa/disable"),
        ("POST", "/v1/auth/mfa/setup"),
        ("POST", "/v1/auth/password-reset/confirm"),
        ("POST", "/v1/auth/password-reset/request"),
        ("POST", "/v1/auth/change-password"),
        ("POST", "/v1/auth/register"),
        ("GET", "/v1/auth/edge-sign"),
        ("POST", "/v1/auth/login"),
        ("POST", "/v1/auth/logout"),
        ("GET", "/v1/auth/me"),
        ("POST", "/v1/auth/refresh"),
        ("POST", "/v1/auth/tenants"),
        ("GET", "/v1/auth/users"),
        ("PATCH", "/v1/auth/users/{user_id}/deactivate"),
        ("PATCH", "/v1/auth/users/{user_id}/role"),
    }
    present_pairs = {(r["method"], r["path"]) for r in rows if r["file"] in auth_files}
    missing = new_paths - present_pairs
    assert not missing, f"auth routers missing expected migrated route(s): {missing}"
    assert len(new_paths) == 24, f"expected 24 auth routes, got {len(new_paths)}"

    auth_legacy = {
        (r["method"], r["path"])
        for r in rows
        if r["service"] == "auth" and r["classification"] == "legacy_unversioned_business"
    }
    assert auth_legacy == set(), (
        f"auth service still has legacy_unversioned_business routes: {sorted(auth_legacy)}"
    )


def test_chat_proxy_reference_is_structurally_unmounted():
    """`POST /api/chat` was counted as legacy migration debt, but the module that
    declares it is a standalone reference example the platform never mounts — the
    inventory was claiming a route the running app does not serve (same class as the
    `GET /probe` test-file false positive fixed on 2026-07-30).

    This proves the three independent structural facts the exclusion rests on, so the
    exclusion is backed by a verified invariant rather than an assertion. If anyone
    ever mounts the module, moves it into `api/routers/`, or gives it a `router`
    export, this fails and forces the exclusion to be re-evaluated."""
    root = Path(__file__).resolve().parents[1]
    module = root / "services" / "sahool-platform" / "api" / "chat_proxy_reference.py"
    assert module.is_file(), "reference module missing — re-evaluate the exclusion"

    # (1) It is NOT inside api/routers/, and register_routers() auto-mounts only that
    #     package (pkgutil.iter_modules over api/routers/).
    assert not (module.parent / "routers" / "chat_proxy_reference.py").exists()
    registry = (module.parent / "router_registry.py").read_text(encoding="utf-8")
    assert "_routers_pkg.__path__" in registry, (
        "router_registry no longer auto-mounts by scanning api/routers/ — "
        "the unmounted-reference exclusion must be re-derived"
    )

    # (2) It exports no `router` object at all — only a standalone FastAPI `app`.
    source = module.read_text(encoding="utf-8")
    assert "FastAPI(" in source
    tree = ast.parse(source)
    exported_routers = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "router"
    }
    assert not exported_routers, "module now exports `router` — it may be auto-mounted"

    # (3) No production module imports it (test harnesses load it via importlib, which
    #     does not mount it into the platform app).
    importers: list[str] = []
    for py in sorted(root.glob("services/**/*.py")):
        if "__pycache__" in py.parts or py == module:
            continue
        if guard._is_test_file(py):
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "chat_proxy_reference" in stripped:
                importers.append(f"{py.relative_to(root).as_posix()}: {stripped}")
    assert not importers, f"module is imported by production code now: {importers}"

    # Therefore it must not appear in the served inventory at all.
    inventoried = {r["file"] for r in guard.collect()}
    assert "services/sahool-platform/api/chat_proxy_reference.py" not in inventoried
