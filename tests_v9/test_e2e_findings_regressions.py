"""Regression guards for defects measured by the 2026-09-02 live E2E pass."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_mfa_router_owns_its_crypto_dependencies():
    source = _source("services/auth/routers/mfa.py")
    tree = ast.parse(source)
    imports = {
        alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names
    }
    assert {"mfa_crypto", "pyotp"} <= imports
    assert "main.mfa_crypto" not in source
    assert "main.pyotp" not in source


def test_market_runtime_tables_are_created_by_forward_migration():
    migration = _source("migrations/v229_market_mcp_schema.sql")
    required = {
        "market_suppliers",
        "market_products",
        "market_price_history",
        "market_procurement_orders",
        "market_procurement_items",
        "market_analytics_snapshots",
    }
    for table in required:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in migration
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in migration
        assert f"CREATE POLICY tenant_isolation ON {table}" in migration
    assert "v229_market_mcp_schema.sql" in _source("migrations/MANIFEST.txt")
    assert _source("migrations/MANIFEST.txt").rstrip().endswith("v206_rls_final_hardening.sql")


def test_market_tenant_guc_is_scoped_by_transaction_context():
    source = _source("services/mcp_servers/market_server.py")
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)}

    def transactions(function: ast.AsyncFunctionDef) -> list[ast.AsyncWith]:
        return [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.AsyncWith)
            and any("transaction()" in ast.unparse(item.context_expr) for item in node.items)
        ]

    assert "async def tenant_connection" in source
    assert len(transactions(functions["tenant_connection"])) == 1
    assert transactions(functions["tool_create_procurement"]) == []
    assert source.count("async with tenant_connection(tenant_id) as conn:") == 10
    assert source.count("set_config('app.current_tenant'") == 1


def test_market_authz_guc_and_visibility_query_share_transaction():
    source = _source("services/mcp_servers/market_db_authz.py")
    tree = ast.parse(source)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "batch_visible_under_tenant"
    )
    transactions = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.AsyncWith) and "transaction()" in ast.unparse(n.items[0].context_expr)
    ]
    assert len(transactions) == 1
    body = ast.unparse(transactions[0])
    assert "set_config" in body and "inventory_batches" in body


@pytest.mark.asyncio
async def test_wofost_invalid_arguments_are_422_not_500(monkeypatch):
    mcp_dir = ROOT / "services" / "mcp_servers"
    monkeypatch.syspath_prepend(str(ROOT))
    monkeypatch.syspath_prepend(str(mcp_dir))
    saved_shared = {
        name: module
        for name, module in sys.modules.items()
        if name == "shared" or name.startswith("shared.")
    }
    for name in saved_shared:
        sys.modules.pop(name, None)
    sys.modules.pop("wofost_server", None)
    try:
        module = importlib.import_module("wofost_server")
        with pytest.raises(HTTPException) as caught:
            await module._execute("run_wofost_simulation", {"crop": "not-a-crop"})
        assert caught.value.status_code == 422
        assert isinstance(caught.value.detail, list)
    finally:
        for name in [n for n in sys.modules if n == "shared" or n.startswith("shared.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved_shared)


def test_compose_wires_mfa_key_and_outbox_switch():
    for compose in ("docker-compose.v9.yml", "docker-compose.fixed.yml"):
        source = _source(compose)
        assert "MFA_SECRET_ENCRYPTION_KEY:" in source
        assert "FEATURE_NATS_PUBLISHERS:" in source
        assert "JOBS_DATABASE_URL:" in source


def test_geometry_revert_decodes_jsonb_strings_before_guarding():
    source = _source("services/sahool-platform/api/routers/fields.py")
    fn = next(
        n
        for n in ast.parse(source).body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "revert_field_geometry"
    )
    rendered = ast.unparse(fn)
    assert "isinstance(raw_geometry, str)" in rendered
    assert "json.loads(raw_geometry)" in rendered
    assert rendered.index("json.loads(raw_geometry)") < rendered.index(
        "guard_field_geometry(raw_geometry)"
    )
    assert "stored_geometry_invalid" in rendered
