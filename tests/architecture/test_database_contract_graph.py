import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "database-audit/generated/database_contract_graph.json"
MARKET_MCP_TABLES = {
    "market_analytics_snapshots",
    "market_price_history",
    "market_procurement_items",
    "market_procurement_orders",
    "market_products",
    "market_suppliers",
}


def load():
    return json.loads(P.read_text(encoding="utf-8"))


def test_database_contract_is_static_only():
    d = load()
    assert d["summary"]["runtime_verified"] is False
    assert d["summary"]["production_certified"] is False


def test_manifest_has_no_missing_files_or_duplicates():
    d = load()
    assert d["manifest"]["missing"] == []
    assert len(d["manifest"]["entries"]) == len(set(d["manifest"]["entries"]))


def test_tables_are_unique_and_sorted():
    d = load()
    names = [x["table"] for x in d["tables"]]
    assert names == sorted(names)
    assert len(names) == len(set(names))


def test_market_mcp_rls_is_visible_to_static_governance():
    rows = {row["table"]: row for row in load()["tables"]}
    assert MARKET_MCP_TABLES <= rows.keys()
    for table in MARKET_MCP_TABLES:
        row = rows[table]
        assert row["rls_enabled"] is True
        assert row["rls_forced"] is True
        assert row["policy_count"] >= 1
        assert row["write_policy_with_check"] is True
        assert row["tenant_rls_gap"] is False


def test_database_contract_drift_gate():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/database_contract_graph.py"), "--check"],
        cwd=ROOT,
        check=True,
    )


def test_rls_and_migration_guards():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/rls_policy_guard.py"), "--check"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/migration_graph_guard.py"), "--check"],
        cwd=ROOT,
        check=True,
    )
