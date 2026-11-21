"""Contract guard for the executable names in the live gap-closure runbook.

The first live run proved that a plausible-looking command can select zero
tests, query a nonexistent column, publish to a dead subject, or call a route
that is not mounted.  These tests bind the runbook to the legal source files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/runbooks/LIVE_GAP_CLOSURE_AGENT_RUNBOOK.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_runbook_does_not_retain_the_invalid_live_references() -> None:
    text = _text(RUNBOOK)
    forbidden = (
        "SELECT status, count(*) FROM execution_ledger",
        "GROUP BY 1,2",
        "nats sub 'actuator.>'",
        "nats pub 'actuator.command'",
        "/api/v1/irrigation/recommendations",
        "pytest -v -m integration tests_v9/test_wx10_11b_execution_delivery_receipt_contract.py",
        # Recalibration 2026-11-21: unmounted routes and nonexistent columns.
        '/api/v1/fields/${FIELD_ID}/canonical-state"',
        "localhost:8000/mcp/v1/tools",
        "localhost:8000/v1/cutover/readiness",
        "SELECT domain, count(*) FROM evidence_graph_nodes",
        "INSERT INTO evidence_graph_nodes (evidence_id",
        "SELECT asset_id, usable, quality_status FROM raster_assets",
    )
    assert not [literal for literal in forbidden if literal in text]


def test_execution_ledger_query_uses_the_migrated_outcome_column() -> None:
    runbook = _text(RUNBOOK)
    migration = _text(ROOT / "migrations/v68_execution_ledger.sql")
    assert "outcome         VARCHAR(16)" in migration
    assert "SELECT outcome, count(*) AS total" in runbook
    assert "GROUP BY outcome" in runbook


def test_actuator_probe_names_the_only_published_dispatch_subject() -> None:
    subject = "sahool.actuator.dispatch.requested"
    runbook = _text(RUNBOOK)
    publisher = _text(ROOT / "services/sahool-platform/api/phase_runtime_workers.py")
    assert subject in publisher
    assert subject in runbook
    assert "SIMULATED_ADAPTER_ONLY" in runbook
    assert "PHYSICAL_DEVICE_NETWORK_DISCONNECTED" in runbook


def test_correlation_kickoff_uses_a_mounted_route_and_submits_to_decision() -> None:
    route = "/api/v1/fields/{field_id}/irrigation-recommendation"
    runbook_route = '"http://localhost:8000/api/v1/fields/${FIELD_ID}/irrigation-recommendation"'
    runbook = _text(RUNBOOK)
    inventory = _text(ROOT / "route_inventory.csv")
    router = _text(ROOT / "services/sahool-platform/api/routers/irrigation_recommendation.py")
    assert route in inventory
    assert '@router.post("/api/v1/fields/{field_id}/irrigation-recommendation")' in router
    assert runbook_route in runbook
    assert "submit_to_decision" in runbook


def test_static_boundary_test_is_not_misrepresented_as_integration() -> None:
    runbook = _text(RUNBOOK)
    boundary_test = _text(ROOT / "tests_v9/test_wx10_11b_execution_delivery_receipt_contract.py")
    assert "pytestmark = pytest.mark.unit" in boundary_test
    assert "pytest -v tests_v9/test_wx10_11b_execution_delivery_receipt_contract.py" in runbook
    assert "اختبار PG الحيّ المنفصل شرط الإغلاق" in runbook


def test_http_probe_uses_a_tool_present_in_the_python_service_image() -> None:
    runbook = _text(RUNBOOK)
    dockerfile = _text(ROOT / "services/ai_agronomist/Dockerfile")
    assert "FROM python:" in dockerfile
    assert "urllib.request" in runbook
    assert "sahool-ai-agronomist python -" in runbook


def test_local_agent_helpers_exist_under_the_operations_namespace() -> None:
    scripts = ROOT / "scripts/ops/live_gap_closure"
    assert (scripts / "run_preflight.sh").is_file()
    assert (scripts / "run_readonly_baseline.sh").is_file()


def test_preflight_does_not_require_unused_ripgrep() -> None:
    helper = _text(ROOT / "scripts/ops/live_gap_closure/run_preflight.sh")
    assert "for cmd in git python; do" in helper
    assert "git python rg" not in helper


def test_readonly_helper_neither_executes_env_file_nor_copies_nats_secrets() -> None:
    helper = _text(ROOT / "scripts/ops/live_gap_closure/run_readonly_baseline.sh")
    assert '. "$ENV_FILE"' not in helper
    assert '--env-file "$ENV_FILE"' in helper
    assert "sed -n" not in helper
    assert "11_nats_security_flags" in helper
    assert "password_present" not in helper  # derived at runtime; never a copied value


def _created_tables(migrations_dir: str) -> set[str]:
    """Tables created by any CREATE TABLE in ``migrations_dir``."""
    import re

    names: set[str] = set()
    for path in sorted((ROOT / migrations_dir).glob("*.sql")):
        sql = re.sub(r"--[^\n]*", "", _text(path))
        names.update(
            m.lower()
            for m in re.findall(
                r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:"?\w+"?\.)?"?(\w+)"?', sql, re.I
            )
        )
    return names


def _migration_columns(table: str, migrations_dir: str = "migrations") -> set[str]:
    """Columns declared for ``table`` by CREATE TABLE / ALTER TABLE ADD COLUMN in ``migrations_dir``."""
    import re

    columns: set[str] = set()
    ident = r'(?:"?\w+"?\.)?"?(\w+)"?'
    for path in sorted((ROOT / migrations_dir).glob("*.sql")):
        if path.name.endswith(".down.sql"):
            continue
        sql = re.sub(r"--[^\n]*", "", _text(path))
        for m in re.finditer(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + ident + r"\s*\(", sql, re.I
        ):
            if m.group(1).lower() != table:
                continue
            depth, j = 1, m.end()
            while j < len(sql) and depth:
                depth += {"(": 1, ")": -1}.get(sql[j], 0)
                j += 1
            for part in re.split(r",(?![^()]*\))", sql[m.end() : j - 1]):
                words = part.strip().split()
                if words:
                    columns.add(words[0].strip('"').lower())
        for m in re.finditer(
            r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?" + ident + r"(.*?);", sql, re.I | re.S
        ):
            if m.group(1).lower() == table:
                for c in re.finditer(
                    r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?(\w+)\"?", m.group(2), re.I
                ):
                    columns.add(c.group(1).lower())
    return columns


def test_runbook_and_preflight_name_the_same_measurement_base() -> None:
    import re

    helper = _text(ROOT / "scripts/ops/live_gap_closure/run_preflight.sh")
    match = re.search(r'BASE_SHA="\$\{BASE_SHA:-([0-9a-f]{40})\}"', helper)
    assert match, "run_preflight.sh must pin a full 40-hex BASE_SHA"
    base = match.group(1)
    runbook = _text(RUNBOOK)
    assert f"إعادة المعايرة الحاليّة (2026-11-21) على `{base}`" in runbook
    assert f"git diff --name-only {base[:9]} HEAD -- migrations/ services/" in runbook
    assert "## سجلّ إعادة المعايرة — 2026-11-21" in runbook


def test_field_state_and_mcp_probes_use_mounted_routes() -> None:
    runbook = _text(RUNBOOK)
    inventory = _text(ROOT / "route_inventory.csv")
    assert ",GET,/api/v1/fields/{field_id}/state,field_canonical_state" in inventory
    assert "canonical-state," not in inventory.replace("/v1/weather/agro/canonical-state,", "")
    assert runbook.count('"http://localhost:8000/api/v1/fields/${FIELD_ID}/state"') == 3
    assert ",GET,/v1/mcp/tools," in inventory
    assert "M=http://localhost:8000/v1/mcp/tools" in runbook
    assert "decision-service,services/decision-service/main.py" in inventory
    assert ",GET,/v1/cutover/readiness,cutover_readiness" in inventory
    assert '"${DECISION_URL:-http://127.0.0.1:8160}/v1/cutover/readiness"' in runbook


def test_evidence_and_raster_probes_name_only_migrated_columns() -> None:
    runbook = _text(RUNBOOK)
    nodes = _migration_columns("evidence_graph_nodes")
    assets = _migration_columns("raster_assets")
    assert {
        "node_type",
        "source",
        "tenant_id",
        "field_id",
        "snapshot_id",
        "node_id",
        "status",
    } <= nodes
    assert not {"domain", "evidence_id", "observed_at"} & nodes
    assert "SELECT node_type, source, count(*) FROM evidence_graph_nodes" in runbook
    assert (
        "INSERT INTO evidence_graph_nodes (tenant_id, field_id, snapshot_id, node_id, node_type, status)"
        in runbook
    )
    assert "ROLLBACK;" in runbook
    assert {"id", "asset_status", "cog_uri", "quality_score", "valid_pixel_ratio"} <= assets
    assert not {"asset_id", "usable", "quality_status"} & assets
    assert (
        "SELECT id, asset_status, cog_uri IS NOT NULL AS has_cog, quality_score, valid_pixel_ratio"
        in runbook
    )


def test_correlation_measurement_matches_the_migrated_decision_chain() -> None:
    runbook = _text(RUNBOOK)
    migration = _text(ROOT / "migrations/v235_decision_chain_correlation.sql")
    for table in (
        "decision_record",
        "dispatch_decisions",
        "execution_ledger",
        "as_applied_irrigation_runs",
        "as_applied_irrigation_receipts",
    ):
        assert f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS correlation_id uuid;" in migration
        assert "correlation_id" in _migration_columns(table)
    assert "root correlation is server-owned" in migration
    # decision_reviews lives in decision-service's own schema, not migrations/, so a
    # migrations/-only scan would return an empty set and prove nothing about it.
    assert "decision_reviews" not in _created_tables("migrations")
    decision_dir = "services/decision-service/migrations"
    assert "decision_reviews" in _created_tables(decision_dir)
    for table in (
        "decision_reviews",
        "decision_execution_plans",
        "decision_dispatch_authorizations",
        "decision_execution_requests",
    ):
        assert "correlation_id" in _migration_columns(table, decision_dir), table
    assert "036_decision_chain_correlation.sql" in runbook
    assert "ما زال بلا عمود" not in runbook
    assert "v235_decision_chain_correlation.sql" in runbook
    assert "**يملكه الخادم**" in runbook


def test_deferred_import_debt_claim_matches_the_contract() -> None:
    import json

    contract = json.loads(
        _text(ROOT / "docs/architecture/deferred_import_declaration_contract.json")
    )
    runbook = _text(RUNBOOK)
    fixed = contract["fixed_in_this_slice"]
    for key in ("sahool-platform:sklearn", "raster-service:yaml", "ai_agronomist:redis"):
        assert key in fixed
    assert contract["undeclared_debt"] == []
    assert "**على `8b644c6d9` صار صفراً:**" in runbook
