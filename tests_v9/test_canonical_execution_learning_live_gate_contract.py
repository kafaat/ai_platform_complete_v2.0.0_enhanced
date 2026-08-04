from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_rls_live_gate_is_fail_closed_and_cross_tenant():
    text = (ROOT / "scripts/e2e/canonical_execution_learning_rls_live_gate.sql").read_text(
        encoding="utf-8"
    )
    assert "NOBYPASSRLS" in text
    assert "relforcerowsecurity" in text
    assert "SET LOCAL ROLE sahool_app" in text
    assert "tenant B can read tenant A" in text
    assert "cross-tenant insert unexpectedly accepted" in text
    assert text.rstrip().endswith("\\echo 'PASS canonical_execution_learning_rls_live_gate'")


def test_unified_live_gate_runs_causality_rls_and_worker_preflight():
    text = (ROOT / "scripts/e2e/run_canonical_execution_learning_live_gate.sh").read_text(
        encoding="utf-8"
    )
    assert "command_event_causality_live_gate.sql" in text
    assert "canonical_execution_learning_rls_live_gate.sql" in text
    assert "canonical_execution_learning_worker.py --preflight" in text
    assert "DATABASE_URL is required" in text


def test_worker_preflight_checks_required_tables_and_jetstream():
    text = (ROOT / "scripts/workers/canonical_execution_learning_worker.py").read_text(
        encoding="utf-8"
    )
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


def test_live_gate_binds_evidence_to_checkout_sha_and_hashes_outputs():
    """Evidence that names no commit certifies nothing.

    A runtime-evidence file is only meaningful if it says WHICH tree was exercised and
    lets a reader re-derive the outputs. The runner therefore pins the checkout SHA
    (refusing to proceed on a mismatch), hashes each check's output, and records
    ``production_certified: False`` — a qualification candidate is not a certification.
    """
    text = (ROOT / "scripts/e2e/run_canonical_execution_learning_live_gate.sh").read_text(
        encoding="utf-8"
    )
    assert "EXPECTED_SHA" in text
    assert "git rev-parse HEAD" in text
    assert "checkout SHA mismatch" in text, "a SHA mismatch must abort, not be recorded"
    assert "output_sha256" in text
    assert "'production_certified': False" in text, (
        "the honesty invariant must survive into the emitted evidence"
    )
    assert "truth_boundary" in text, "evidence must state what it does NOT prove"
    assert "LIVE_EVIDENCE_OUTPUT" in text


def test_worker_preflight_json_reports_subject_to_stream_mapping():
    """Preflight must report the facts it checked, not merely exit zero."""
    path = ROOT / "scripts/workers/canonical_execution_learning_worker.py"
    text = path.read_text(encoding="utf-8")
    assert "subject_streams" in text
    assert "find_stream_name_by_subject" in text
    assert '"required_tables": tables' in text

    # Flags read from the parsed CLI, never from a source substring: the substring form
    # broke once already when `ruff format` reflowed the call.
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
    assert {"--preflight", "--preflight-json"} <= flags, f"found {sorted(flags)}"


def test_the_jetstream_roundtrip_proves_consumption_not_merely_connectivity():
    """Subject coverage is not message processing — the round trip must close the loop.

    Preflight proves a stream exists for each subject. That is connectivity, and the
    earlier evidence said so in its own truth_boundary. This script publishes a real
    identifiers-only event, waits for the REGISTERED worker to persist the canonical row
    and its outbox intent, republishes the identical event to prove replay creates
    nothing new, and removes its fixture. It also re-checks live what a fake connection
    never could: that the emitted event carries no synthesised command_id.
    """
    path = ROOT / "scripts/e2e/canonical_projection_jetstream_roundtrip.py"
    text = path.read_text(encoding="utf-8")
    assert "canonical_projection_requests" in text
    assert "sahool.events.agronomy.projection.requested" in text
    assert "synthetic command_id" in text, (
        "the round trip must assert the FK-safe command id on a live event"
    )
    assert "replay created duplicate canonical state or outbox intent" in text
    assert "DELETE FROM canonical_projection_requests" in text, "the fixture must be removed"

    runner = (ROOT / "scripts/e2e/run_canonical_execution_learning_live_gate.sh").read_text(
        encoding="utf-8"
    )
    assert "canonical_projection_jetstream_roundtrip.py" in runner, (
        "a round trip nothing runs proves nothing"
    )
    assert "jetstream_projection_roundtrip" in runner, "its result must enter the evidence"
    assert "It does not prove soak, disaster recovery, or production certification" in runner, (
        "the truth boundary must still disclaim what the round trip does not establish"
    )
