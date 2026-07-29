"""FII Increment 2c — the chemical-lineage guard is a single shared source.

The canonical guard lives in ``shared/governance/chemical_lineage.py`` so every
service (decision-service / actuator-service / odoo-bridge) imports the SAME audit
at its own CHEMICAL_INTERVENTION boundary. The platform module re-exports it, so
there is exactly one implementation (no drift). tests_v9 has both the repo root and
services/sahool-platform on sys.path (see conftest), so both imports resolve here.
"""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit


def test_shared_governance_module_is_importable():
    mod = importlib.import_module("shared.governance.chemical_lineage")
    for name in (
        "audit_chemical_lineage",
        "ChemicalBoundary",
        "ViolationCode",
        "ResolverUnavailable",
    ):
        assert hasattr(mod, name), name


def test_platform_reexports_the_shared_singleton():
    shared = importlib.import_module("shared.governance.chemical_lineage")
    core = importlib.import_module("core.chemical_lineage")
    # Identity, not just equality: platform must re-export the shared object so there
    # is a single source of truth (no forked copy that could drift).
    assert core.audit_chemical_lineage is shared.audit_chemical_lineage
    assert core.ChemicalBoundary is shared.ChemicalBoundary
    assert core.ViolationCode is shared.ViolationCode


def test_shared_audit_runs_and_is_audit_only(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")
    shared = importlib.import_module("shared.governance.chemical_lineage")
    r = shared.audit_chemical_lineage(
        field_id=None,
        season_id=None,
        diagnosis_ref=None,
        evidence_ref=None,
        boundary=shared.ChemicalBoundary.EXECUTE,
    )
    assert r.mode == "audit"
    assert not r.compliant  # violations reported...
    assert shared.ViolationCode.MISSING_FIELD_ID.value in r.violations  # ...with stable codes
