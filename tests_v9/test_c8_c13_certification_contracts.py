from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {
    f"C{i}": ROOT / f"scripts/ci/c{i}_{name}"
    for i, name in [
        (8, "rag_production_certification.py"),
        (9, "decision_authority_certification.py"),
        (10, "field_authority_certification.py"),
        (11, "closed_loop_lineage_certification.py"),
        (12, "governed_learning_promotion_certification.py"),
        (13, "physical_shrink_certification.py"),
    ]
}


def run(stage, *args, env=None):
    p = subprocess.run(
        [sys.executable, str(SCRIPTS[stage]), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        check=False,
        timeout=60,
    )
    return p.returncode, json.loads(p.stdout)


def test_offline_stages_fail_closed_without_promoting_authority():
    for stage in ("C8", "C9", "C10", "C11", "C12"):
        env = os.environ.copy()
        env.pop("DATABASE_URL", None)
        rc, o = run(stage, env=env)
        assert rc == 0 and o["status"] == "EVIDENCE_REQUIRED", (stage, o)
        assert o.get("authority_changed", False) is False


def test_c11_never_runs_live_from_database_url_alone():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://example.invalid/db"
    rc, o = run("C11", env=env)
    assert rc == 0 and o["status"] == "EVIDENCE_REQUIRED"
    assert o["findings"] == ["explicit_live_execution_required"]
    assert o["live_execution"] is False


def test_c11_live_mode_requires_subject_before_any_migration():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://example.invalid/db"
    rc, o = run("C11", "--live", env=env)
    assert rc == 1 and o["status"] == "FAILED"
    assert "full_40_char_subject_sha_required" in o["findings"]


def test_c13_is_idempotent_and_does_not_lower_a_numeric_baseline():
    rc, o = run("C13")
    assert rc == 0 and o["status"] == "PASS" and o["already_closed"] is True
    assert o["physical_shrink_authorized"] is False
    assert not (ROOT / "services/sahool-platform/core/knowledge_graph/sqlite_graph.py").exists()


def test_wrappers_delegate_to_canonical_guards_instead_of_redefining_receipts():
    expected = {
        "C8": (
            "rag_authority_convergence_guard.py",
            "rag_operational_boundary_guard.py",
            "rag_live_parity_receipt_guard.py",
        ),
        "C9": ("authority_cutover_guard.py", "s5_decision_live_closure_receipt_guard.py"),
        "C10": ("authority_cutover_guard.py", "s4_field_rls_receipt_guard.py"),
        "C11": ("certify_agronomic_lineage.py",),
        "C12": (
            "model_promotion_decision_boundary_gate.py",
            "model_activation_request_boundary_gate.py",
            "model_activation_approval_boundary_gate.py",
            "model_registry_activation_boundary_gate.py",
            "wx11_closed_loop_completion_gate.py",
        ),
        "C13": ("platform_shrink_ratchet_guard.py",),
    }
    for stage, names in expected.items():
        text = SCRIPTS[stage].read_text(encoding="utf-8")
        for name in names:
            assert name in text, (stage, name)
    # C8-C10 must not implement their own receipt field validation language.
    for stage in ("C8", "C9", "C10"):
        text = SCRIPTS[stage].read_text(encoding="utf-8")
        for forbidden in (
            "rolsuper",
            "rolbypassrls",
            "min_jaccard",
            "cross_tenant_read_blocked",
            "db_revoke_grant_proof",
        ):
            assert forbidden not in text, (stage, forbidden)


def test_execution_contract_forbids_parallel_certification_truth_layer():
    c = json.loads(
        (ROOT / "docs/architecture/c8_c13_execution_contract.json").read_text(encoding="utf-8")
    )
    assert c["schema"] == "sahool.c8-c13-execution-contract/v2"
    assert "no_parallel_certification_truth_layer" in c["invariants"]
    assert all(s.get("authority_change") is False for s in c["sequence"][:4])
    assert c["sequence"][4]["automatic_promotion"] is False


def test_ci_wires_c8_c13_wrappers_without_live_receipt_fabrication():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for p in SCRIPTS.values():
        assert p.name in ci
    assert "--receipt" not in "\n".join(
        line for line in ci.splitlines() if "c8_" in line or "c9_" in line or "c10_" in line
    )
