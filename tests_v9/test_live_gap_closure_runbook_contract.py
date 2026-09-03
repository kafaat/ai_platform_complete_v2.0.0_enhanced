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
