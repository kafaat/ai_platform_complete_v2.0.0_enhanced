"""Regression proof for CHECK-STEPS-MUTATE-THE-TREE-01.

Every command advertised as ``--check`` must be observational: it may build a
candidate outside the repository, but it must not rewrite its committed outputs.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]

CASES = [
    (
        "service_inventory",
        [sys.executable, "scripts/ci/generate_service_inventory.py", "--check"],
        [
            "service_inventory.generated.json",
            "route_inventory.generated.json",
            "service_inventory.csv",
            "route_inventory.csv",
            "SERVICE_REGISTRY.md",
        ],
    ),
    (
        "execution_dependency_audit",
        [sys.executable, "scripts/ci/execution_dependency_audit.py", "--check"],
        [
            "execution-audit/generated/execution_dependency_audit.json",
            "execution-audit/generated/execution_audit_summary.json",
            "execution-audit/generated/route_handlers.csv",
            "execution-audit/generated/dead_code_candidates.csv",
            "execution-audit/generated/EXECUTION_DEPENDENCY_AUDIT_REPORT.md",
            "execution-audit/generated/.audit.sha256",
        ],
    ),
    (
        "capability_runtime_evidence",
        [sys.executable, "scripts/ci/capability_runtime_evidence.py", "--check"],
        [
            "capabilities/generated/capability_runtime_evidence_summary.json",
            "capabilities/generated/capability_runtime_evidence.csv",
            "capabilities/generated/CAPABILITY_RUNTIME_EVIDENCE_REPORT.md",
            "capabilities/registry/capabilities.json",
        ],
    ),
    (
        "dependency_conflicts",
        [sys.executable, "scripts/ci/service_dependency_conflict_guard.py", "--check"],
        ["dependency_conflicts.generated.json", "dependency_conflicts.csv"],
    ),
    (
        "route_mount_inventory",
        [sys.executable, "scripts/ci/route_mount_contract_guard.py", "--check"],
        ["route_mount_inventory.generated.json", "route_mount_inventory.csv"],
    ),
    (
        "raw_data_processing_contract",
        [sys.executable, "scripts/ci/raw_data_processing_contract_guard.py", "--check"],
        ["raw_data_processing_contract.generated.json"],
    ),
]

LF_OWNED_OUTPUTS = [
    "api_versioning_inventory.csv",
    "capabilities/generated/capability_link_candidates.csv",
    "database-audit/generated/database_tables.csv",
    "docs/capability-registry/generated/mapping/capability_mapping.csv",
    "execution-audit/generated/dead_code_candidates.csv",
    "execution-audit/generated/route_handlers.csv",
    "route_inventory.csv",
    "service_inventory.csv",
]


def _snapshot(paths: list[str]) -> dict[str, tuple[str, int, int]]:
    result: dict[str, tuple[str, int, int]] = {}
    for rel in paths:
        path = ROOT / rel
        assert path.is_file(), f"missing committed output: {rel}"
        stat = path.stat()
        result[rel] = (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            stat.st_mtime_ns,
            stat.st_mode,
        )
    return result


def test_changed_generated_csv_outputs_use_deterministic_lf() -> None:
    """CRLF makes changed generated rows fail ``git diff --check`` as whitespace."""
    for rel in LF_OWNED_OUTPUTS:
        payload = (ROOT / rel).read_bytes()
        assert b"\r\n" not in payload, f"generated CSV must use LF: {rel}"


@pytest.mark.parametrize(("name", "command", "outputs"), CASES, ids=[c[0] for c in CASES])
def test_check_command_does_not_mutate_owned_outputs(
    name: str, command: list[str], outputs: list[str]
) -> None:
    before = _snapshot(outputs)
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=240)
    assert result.returncode == 0, result.stdout + result.stderr
    after = _snapshot(outputs)
    assert after == before, f"{name} mutated committed outputs during --check"
