from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_rls_live_gate_is_fail_closed_and_cross_tenant():
    text = (ROOT / "scripts/e2e/canonical_execution_learning_rls_live_gate.sql").read_text()
    assert "NOBYPASSRLS" in text
    assert "relforcerowsecurity" in text
    assert "SET LOCAL ROLE sahool_app" in text
    assert "tenant B can read tenant A" in text
    assert "cross-tenant insert unexpectedly accepted" in text
    assert text.rstrip().endswith("\\echo 'PASS canonical_execution_learning_rls_live_gate'")


def test_unified_live_gate_runs_causality_rls_and_worker_preflight():
    text = (ROOT / "scripts/e2e/run_canonical_execution_learning_live_gate.sh").read_text()
    assert "command_event_causality_live_gate.sql" in text
    assert "canonical_execution_learning_rls_live_gate.sql" in text
    assert "canonical_execution_learning_worker.py --preflight" in text
    assert "DATABASE_URL is required" in text


def test_worker_preflight_checks_required_tables_and_jetstream():
    text = (ROOT / "scripts/workers/canonical_execution_learning_worker.py").read_text()
    assert "async def preflight()" in text
    assert "decision_learning_runs" in text
    assert "irrigation_closed_loop_records" in text
    assert "await js.account_info()" in text

    # Measured on the parsed module, not on a source substring. The substring form
    # (`'parser.add_argument("--preflight"' in text`) broke the moment `ruff format`
    # — itself a blocking gate — reflowed the call across lines: a true property
    # reported as a regression by a test that was reading formatting, not behaviour.
    tree = ast.parse(text)
    flags = {
        arg.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        for arg in node.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    }
    assert "--preflight" in flags, f"worker must expose a --preflight flag; found {sorted(flags)}"
