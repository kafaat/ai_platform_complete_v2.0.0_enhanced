"""IRR-F01 Phase 0 — ownership/convergence contract (no DB).

Locks the ownership boundary before any capacity/reservation migration lands:
the ADR + machine-readable mapping exist, the guard is green, no convergence-era
migration introduces a parallel SoR, and v170's water-allocation ledger is not
mutated by a later migration. The v195 capacity/reservation slice is verified by
its own tests once it lands (Phase 2).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs" / "architecture" / "ADR-IRR-F01-OWNERSHIP.md"
MAPPING = ROOT / "docs" / "architecture" / "irrigation_convergence_mapping.yml"
GUARD = ROOT / "scripts" / "ci" / "irrigation_convergence_guard.py"
MIGRATIONS = ROOT / "migrations"

FORBIDDEN_TABLES = ("irrigation_assets", "irrigation_executions", "irrigation_execution_evidence")


def test_ownership_artifacts_exist() -> None:
    assert ADR.exists(), "ADR-IRR-F01-OWNERSHIP.md missing"
    assert MAPPING.exists(), "irrigation_convergence_mapping.yml missing"
    mapping = MAPPING.read_text(encoding="utf-8")
    for token in FORBIDDEN_TABLES:
        assert token in mapping, f"mapping must declare forbidden table {token}"
    # Precise quota-ledger ban + deferred topology tables must be declared.
    assert "forbidden_quota_ledger_add_columns" in mapping
    assert "allocated_flow_m3h" in mapping
    assert "deferred_topology_tables" in mapping
    assert "irrigation_water_allocations" in mapping


def test_convergence_guard_is_green() -> None:
    completed = subprocess.run(
        [sys.executable, str(GUARD)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_no_convergence_era_migration_creates_parallel_sor() -> None:
    create_re = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-zA-Z_][\w]*)", re.I
    )
    for path in sorted(MIGRATIONS.glob("v*.sql")):
        match = re.match(r"v(\d+)", path.name)
        if not match or int(match.group(1)) < 195:
            continue
        created = {name.lower() for name in create_re.findall(path.read_text(encoding="utf-8"))}
        assert not (created & set(FORBIDDEN_TABLES)), f"{path.name} creates a parallel SoR"
