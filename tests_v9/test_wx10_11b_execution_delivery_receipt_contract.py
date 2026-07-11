from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[1]


def test_migration_and_routes_present():
    migration = (
        ROOT / "services/decision-service/migrations/006_execution_delivery_receipt.sql"
    ).read_text()
    main = (ROOT / "services/decision-service/main.py").read_text()
    assert "decision_execution_delivery_attempts" in migration
    assert "'delivering'" in migration
    assert "/v1/execution-requests/{execution_request_id}/claim" in main
    assert "/v1/execution-requests/{execution_request_id}/receipt" in main


def test_receipt_is_terminal_and_no_outcome_side_effect():
    persistence = (ROOT / "services/decision-service/persistence.py").read_text()
    # Bound to the record_execution_receipt function only (up to the next top-level async def):
    # WX-10.12 verify_execution_outcome follows it and legitimately reads/writes outcome_record,
    # so slicing to EOF would false-trip. The contract is that the RECEIPT itself is terminal.
    start = persistence.index("async def record_execution_receipt")
    rest = persistence[start + len("async def record_execution_receipt") :]
    nxt = rest.find("\nasync def ")
    block = rest if nxt == -1 else rest[:nxt]
    assert "EXECUTION_RECEIPT_RECORDED" in block
    assert "outcome_record" not in block
    assert "online_learning_updates" not in block


def test_boundary_guard_runs():
    import runpy

    runpy.run_path(str(ROOT / "scripts/ci/execution_delivery_receipt_boundary_gate.py"))
