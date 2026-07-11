import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "services/decision-service/main.py"
PERSIST = ROOT / "services/decision-service/persistence.py"
MIG = ROOT / "services/decision-service/migrations/003_execution_plan.sql"
BFF = ROOT / "services/sahool-platform/api/routers/decision_review.py"


def test_python_compiles():
    for p in (MAIN, PERSIST, BFF):
        ast.parse(p.read_text(encoding="utf-8"))


def test_migration_is_additive_append_only_and_planned_only():
    text = MIG.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS decision_execution_plans" in text
    assert "status = 'planned'" in text
    assert "BEFORE UPDATE OR DELETE" in text
    assert "uq_execution_plan_tenant_decision" in text
    assert "uq_execution_plan_tenant_idem" in text


def test_endpoint_is_fail_closed_and_no_execution_side_effects():
    text = MAIN.read_text(encoding="utf-8")
    assert "/v1/decisions/{decision_id}/execution-plan" in text
    assert "if not sor_enabled()" in text
    tree = ast.parse(text)
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
        and n.name == "build_execution_plan"
    )
    executable = ast.dump(fn, include_attributes=False).lower()
    for forbidden in ("record_dispatch", "create_task", "equipment_command", "actuator"):
        assert forbidden not in executable


def test_persistence_requires_approved_review_and_preserves_lineage():
    text = PERSIST.read_text(encoding="utf-8")
    assert 'source["review_state"] != "approved"' in text
    assert 'source["new_state"] != "approved"' in text
    assert "candidate_lineage_mismatch" in text
    assert "review_id_mismatch" in text
    assert "EXECUTION_PLAN_CREATED" in text


def test_bff_requires_authoritative_proof():
    text = BFF.read_text(encoding="utf-8")
    assert "/api/v1/decisions/{decision_id}/execution-plan" in text
    assert 'result.get("authoritative") is True' in text
    assert 'result.get("persisted") is True' in text
    assert 'result.get("plan_state") == "planned"' in text
