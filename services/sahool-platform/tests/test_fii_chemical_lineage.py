"""Backward-compatible surface of the chemical-lineage audit.

Increment 2 hardened the audit (uppercase stable ViolationCode strings + resolver-
backed diagnosis validation). The exhaustive reason-code/boundary matrix lives in
test_fii_chemical_lineage_hardened.py; this file keeps the original contract green.
"""

from core.chemical_lineage import (
    ChemicalBoundary,
    DiagnosisFacts,
    audit_chemical_lineage,
)

DIGEST = "a" * 64
GOOD_EVIDENCE = f"e1@{DIGEST}"


class _ValidResolver:
    def resolve(self, *, tenant_id, diagnosis_ref):
        return DiagnosisFacts(
            found=True,
            tenant_id=tenant_id,
            field_id="fld",
            season_id="s1",
            review_state="supported",
            evidence_level=3,
        )


def test_audit_reports_missing_lineage(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")
    out = audit_chemical_lineage(
        field_id="fld", season_id=None, diagnosis_ref=None, evidence_ref=None
    )
    assert not out.compliant
    assert out.boundary == "draft"
    assert set(out.violations) == {
        "MISSING_SEASON_ID",
        "MISSING_DIAGNOSIS_REF",
        "MISSING_EVIDENCE_REF",
    }


def test_complete_draft_does_not_require_approval(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")
    out = audit_chemical_lineage(
        field_id="fld", season_id="s1", diagnosis_ref="d1", evidence_ref=GOOD_EVIDENCE
    )
    assert out.compliant


def test_execution_requires_human_approval(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")
    out = audit_chemical_lineage(
        field_id="fld",
        season_id="s1",
        diagnosis_ref="d1",
        evidence_ref=GOOD_EVIDENCE,
        tenant_id="fld",
        boundary=ChemicalBoundary.EXECUTE,
        human_approval=False,
        resolver=_ValidResolver(),
    )
    assert not out.compliant
    assert out.violations == ("MISSING_HUMAN_APPROVAL",)


def test_execution_with_approval_is_compliant(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "audit")
    out = audit_chemical_lineage(
        field_id="fld",
        season_id="s1",
        diagnosis_ref="d1",
        evidence_ref=GOOD_EVIDENCE,
        tenant_id="fld",
        boundary=ChemicalBoundary.EXECUTE,
        human_approval=True,
        resolver=_ValidResolver(),
    )
    assert out.compliant


def test_invalid_mode_falls_back_to_audit(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", "unexpected")
    out = audit_chemical_lineage(
        field_id="fld", season_id=None, diagnosis_ref=None, evidence_ref=None
    )
    assert out.mode == "audit"
