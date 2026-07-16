"""FII Increment 2 — P0 hardening (forensic-review fixes).

Locks the P0 fixes from the deep forensic review:
  1. No default network resolver — a missing resolver is VALIDATION_UNAVAILABLE, not a
     silent pass and NOT an implicit HTTP call.
  2. Unknown/misspelled boundary is UNKNOWN_BOUNDARY and fail-closed (strongest), never
     silently coerced to DRAFT.
  3. A missing caller tenant on a validating boundary is MISSING_TENANT_ID.
  4. An incomplete owner response (found=True but required facts absent) is NOT a
     validation (validated stays False) and records OWNER_*_MISSING + OWNER_FACTS_INCOMPLETE.
  5. enforce is honored only with FII_CHEMICAL_LINEAGE_ENFORCE_READY=true.
  6. The audit never raises — a resolver blowing up (any Exception) → VALIDATION_UNAVAILABLE.

Pure-logic: no DB, no HTTP, no fastapi.
"""

from __future__ import annotations

import pytest
from core.chemical_lineage import (
    ChemicalBoundary,
    ChemicalLineageMode,
    DiagnosisFacts,
    ViolationCode,
    audit_chemical_lineage,
    effective_mode,
)

DIGEST = "a" * 64
GOOD_EVIDENCE = f"obs-1@{DIGEST}"


def _codes(r):
    return set(r.violations)


def _base(**over):
    args = dict(
        field_id="f1",
        season_id="s1",
        diagnosis_ref="d1",
        evidence_ref=GOOD_EVIDENCE,
        tenant_id="t1",
        boundary=ChemicalBoundary.SUBMIT,
    )
    args.update(over)
    return args


# 1) no default network resolver ------------------------------------------------
def test_missing_resolver_is_validation_unavailable_no_io(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")
    # No resolver injected: must NOT construct a default HTTP resolver / do I/O.
    r = audit_chemical_lineage(resolver=None, **_base(boundary=ChemicalBoundary.SUBMIT))
    assert ViolationCode.VALIDATION_UNAVAILABLE.value in _codes(r)
    assert not r.validated and not r.compliant


# 2) unknown boundary -----------------------------------------------------------
def test_unknown_boundary_is_flagged_and_fail_closed(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")
    r = audit_chemical_lineage(resolver=None, **_base(boundary="execute_now", human_approval=False))
    assert r.boundary == "unknown"
    assert ViolationCode.UNKNOWN_BOUNDARY.value in _codes(r)
    # fail-closed at strongest boundary ⇒ requires validation (unavailable) AND approval
    assert ViolationCode.VALIDATION_UNAVAILABLE.value in _codes(r)
    assert ViolationCode.MISSING_HUMAN_APPROVAL.value in _codes(r)
    assert not r.compliant


def test_unknown_boundary_not_coerced_to_draft(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")
    r = audit_chemical_lineage(resolver=None, **_base(boundary="drafte"))  # typo of draft
    assert r.boundary != "draft"
    assert ViolationCode.UNKNOWN_BOUNDARY.value in _codes(r)


# 3) missing tenant -------------------------------------------------------------
@pytest.mark.parametrize("tenant", [None, "", "   "])
def test_missing_tenant_on_validating_boundary(monkeypatch, tenant):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")
    r = audit_chemical_lineage(resolver=None, **_base(tenant_id=tenant))
    assert ViolationCode.MISSING_TENANT_ID.value in _codes(r)
    assert not r.validated


# 4) incomplete owner facts -----------------------------------------------------
class _Resolver:
    def __init__(self, facts):
        self._facts = facts
        self.calls = 0

    def resolve(self, *, tenant_id, diagnosis_ref):
        self.calls += 1
        return self._facts


def test_incomplete_owner_facts_do_not_validate(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")
    # found=True but every required fact absent
    fr = _Resolver(DiagnosisFacts(found=True))
    r = audit_chemical_lineage(resolver=fr, **_base(boundary=ChemicalBoundary.SUBMIT))
    assert fr.calls == 1
    assert not r.validated  # incomplete owner response is NOT a validation
    c = _codes(r)
    assert ViolationCode.OWNER_FACTS_INCOMPLETE.value in c
    assert ViolationCode.OWNER_TENANT_MISSING.value in c
    assert ViolationCode.OWNER_FIELD_MISSING.value in c
    assert ViolationCode.OWNER_SEASON_MISSING.value in c
    assert ViolationCode.OWNER_EVIDENCE_LEVEL_MISSING.value in c


def test_complete_owner_facts_do_validate(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")
    fr = _Resolver(
        DiagnosisFacts(
            found=True,
            tenant_id="t1",
            field_id="f1",
            season_id="s1",
            review_state="supported",
            evidence_level=3,
        )
    )
    r = audit_chemical_lineage(resolver=fr, **_base(boundary=ChemicalBoundary.SUBMIT))
    assert r.validated and r.compliant


# 5) enforce readiness gate -----------------------------------------------------
def test_enforce_degrades_to_audit_without_ready(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "enforce")
    monkeypatch.delenv("FII_CHEMICAL_LINEAGE_ENFORCE_READY", raising=False)
    assert effective_mode() is ChemicalLineageMode.AUDIT
    r = audit_chemical_lineage(resolver=None, **_base())
    assert r.mode == "audit"


def test_enforce_honored_only_with_ready_flag(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "enforce")
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_ENFORCE_READY", "true")
    assert effective_mode() is ChemicalLineageMode.ENFORCE
    r = audit_chemical_lineage(resolver=None, **_base())
    assert r.mode == "enforce"


# 6) never raises on a hostile resolver ----------------------------------------
def test_resolver_raising_any_exception_becomes_validation_unavailable(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")

    class Boom:
        def resolve(self, *, tenant_id, diagnosis_ref):
            raise RuntimeError("json/protocol blew up")  # not ResolverUnavailable

    r = audit_chemical_lineage(resolver=Boom(), **_base(boundary=ChemicalBoundary.SUBMIT))
    assert ViolationCode.VALIDATION_UNAVAILABLE.value in _codes(r)
    assert not r.validated
