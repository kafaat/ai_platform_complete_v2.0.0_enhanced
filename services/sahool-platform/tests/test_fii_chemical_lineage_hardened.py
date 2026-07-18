"""FII Increment 2 (Audit Hardening) — full reason-code + boundary matrix.

Pure-logic unit tests: no DB, no HTTP, no fastapi. The diagnosis owner is stubbed
with an injected resolver so every ViolationCode and every boundary is exercised
deterministically. Verifies audit-only semantics (violations reported, never raised)
and that a resolver failure surfaces VALIDATION_UNAVAILABLE (never a silent pass).
"""

from __future__ import annotations

import pytest
from core.chemical_lineage import (
    ChemicalBoundary,
    DiagnosisFacts,
    ResolverUnavailable,
    ViolationCode,
    audit_chemical_lineage,
)

DIGEST = "a" * 64
GOOD_EVIDENCE = f"obs-123@{DIGEST}"


class FakeResolver:
    def __init__(self, facts=None, unavailable=False):
        self._facts = facts
        self._unavailable = unavailable
        self.calls = 0

    def resolve(self, *, tenant_id, diagnosis_ref):
        self.calls += 1
        if self._unavailable:
            raise ResolverUnavailable("stub unavailable")
        return self._facts


def _valid_facts(**over):
    base = dict(
        found=True,
        tenant_id="t1",
        field_id="f1",
        season_id="s1",
        review_state="supported",
        evidence_level=3,
        insufficient_evidence=False,
        valid_until=None,
        superseded_by=None,
    )
    base.update(over)
    return DiagnosisFacts(**base)


def _audit(monkeypatch, *, boundary, resolver=None, mode="audit", **kw):
    monkeypatch.setenv("FII_CHEMICAL_LINEAGE_MODE", mode)
    args = dict(
        field_id="f1",
        season_id="s1",
        diagnosis_ref="d1",
        evidence_ref=GOOD_EVIDENCE,
        tenant_id="t1",
        boundary=boundary,
    )
    args.update(kw)
    return audit_chemical_lineage(resolver=resolver, **args)


def codes(result):
    return set(result.violations)


# ── mode gates ────────────────────────────────────────────────────────────────
def test_off_mode_short_circuits(monkeypatch):
    r = _audit(monkeypatch, boundary=ChemicalBoundary.EXECUTE, mode="off", field_id=None)
    assert r.compliant and r.violations == ()


def test_fully_valid_submit_is_compliant_and_validated(monkeypatch):
    fr = FakeResolver(facts=_valid_facts())
    r = _audit(monkeypatch, boundary=ChemicalBoundary.SUBMIT, resolver=fr)
    assert r.compliant, r.violations
    assert r.validated and fr.calls == 1


# ── presence + digest (DRAFT: no resolver call) ────────────────────────────────
@pytest.mark.parametrize(
    "override,expected",
    [
        (dict(field_id=None), ViolationCode.MISSING_FIELD_ID),
        (dict(season_id=None), ViolationCode.MISSING_SEASON_ID),
        (dict(diagnosis_ref=None), ViolationCode.MISSING_DIAGNOSIS_REF),
        (dict(evidence_ref=None), ViolationCode.MISSING_EVIDENCE_REF),
        (dict(evidence_ref="no-digest-here"), ViolationCode.EVIDENCE_DIGEST_MISSING),
    ],
)
def test_presence_and_digest_codes(monkeypatch, override, expected):
    fr = FakeResolver(facts=_valid_facts())
    r = _audit(monkeypatch, boundary=ChemicalBoundary.DRAFT, resolver=fr, **override)
    assert expected.value in codes(r)
    assert not r.compliant


def test_draft_does_not_consult_resolver(monkeypatch):
    fr = FakeResolver(unavailable=True)  # would raise if called
    r = _audit(monkeypatch, boundary=ChemicalBoundary.DRAFT, resolver=fr)
    assert fr.calls == 0
    assert ViolationCode.VALIDATION_UNAVAILABLE.value not in codes(r)
    assert r.compliant  # presence all-good, no validation required at draft


# ── resolver-backed validation (SUBMIT and stronger) ───────────────────────────
def test_validation_unavailable_is_not_a_pass(monkeypatch):
    fr = FakeResolver(unavailable=True)
    r = _audit(monkeypatch, boundary=ChemicalBoundary.SUBMIT, resolver=fr)
    assert ViolationCode.VALIDATION_UNAVAILABLE.value in codes(r)
    assert not r.compliant and not r.validated  # never a silent success


def test_diagnosis_not_found(monkeypatch):
    fr = FakeResolver(facts=DiagnosisFacts(found=False))
    r = _audit(monkeypatch, boundary=ChemicalBoundary.SUBMIT, resolver=fr)
    assert ViolationCode.DIAGNOSIS_NOT_FOUND.value in codes(r)


@pytest.mark.parametrize(
    "facts_over,expected",
    [
        (dict(valid_until="2000-01-01T00:00:00Z"), ViolationCode.DIAGNOSIS_EXPIRED),
        (dict(valid_until="not-a-date"), ViolationCode.DIAGNOSIS_EXPIRED),
        (dict(superseded_by="d2"), ViolationCode.DIAGNOSIS_SUPERSEDED),
        (dict(review_state="pending"), ViolationCode.REVIEW_STATE_NOT_ALLOWED),
        (dict(review_state="not_supported"), ViolationCode.REVIEW_STATE_NOT_ALLOWED),
        (dict(insufficient_evidence=True), ViolationCode.DIAGNOSIS_INSUFFICIENT_EVIDENCE),
        (dict(evidence_level=0), ViolationCode.EVIDENCE_INSUFFICIENT),
        (dict(tenant_id="OTHER"), ViolationCode.TENANT_MISMATCH),
        (dict(field_id="OTHER"), ViolationCode.FIELD_MISMATCH),
        (dict(season_id="OTHER"), ViolationCode.SEASON_MISMATCH),
    ],
)
def test_diagnosis_validity_codes(monkeypatch, facts_over, expected):
    fr = FakeResolver(facts=_valid_facts(**facts_over))
    r = _audit(monkeypatch, boundary=ChemicalBoundary.SUBMIT, resolver=fr)
    assert expected.value in codes(r), r.violations
    assert not r.compliant


def test_evidence_level_threshold_is_configurable(monkeypatch):
    monkeypatch.setenv("FII_CHEMICAL_EVIDENCE_LEVEL_MIN", "4")
    fr = FakeResolver(facts=_valid_facts(evidence_level=3))
    r = _audit(monkeypatch, boundary=ChemicalBoundary.SUBMIT, resolver=fr)
    assert ViolationCode.EVIDENCE_INSUFFICIENT.value in codes(r)


# ── human approval (APPROVE and stronger) ──────────────────────────────────────
@pytest.mark.parametrize(
    "boundary", [ChemicalBoundary.APPROVE, ChemicalBoundary.DISPATCH, ChemicalBoundary.EXECUTE]
)
def test_execution_boundaries_require_human_approval(monkeypatch, boundary):
    fr = FakeResolver(facts=_valid_facts())
    r = _audit(monkeypatch, boundary=boundary, resolver=fr, human_approval=False)
    assert ViolationCode.MISSING_HUMAN_APPROVAL.value in codes(r)
    r2 = _audit(monkeypatch, boundary=boundary, resolver=fr, human_approval=True)
    assert ViolationCode.MISSING_HUMAN_APPROVAL.value not in codes(r2)


def test_submit_does_not_require_human_approval(monkeypatch):
    fr = FakeResolver(facts=_valid_facts())
    r = _audit(monkeypatch, boundary=ChemicalBoundary.SUBMIT, resolver=fr, human_approval=False)
    assert ViolationCode.MISSING_HUMAN_APPROVAL.value not in codes(r)


# ── all covered boundaries actually run validation ─────────────────────────────
@pytest.mark.parametrize(
    "boundary",
    [
        ChemicalBoundary.SUBMIT,
        ChemicalBoundary.WORK_ORDER,
        ChemicalBoundary.APPROVE,
        ChemicalBoundary.INVENTORY_RESERVE,
        ChemicalBoundary.DISPATCH,
        ChemicalBoundary.ACTUATOR_DISPATCH,
        ChemicalBoundary.EXECUTE,
    ],
)
def test_all_non_draft_boundaries_consult_resolver(monkeypatch, boundary):
    fr = FakeResolver(facts=_valid_facts())
    _audit(monkeypatch, boundary=boundary, resolver=fr, human_approval=True)
    assert fr.calls == 1


def test_audit_mode_never_raises(monkeypatch):
    # Even with every field missing and resolver unavailable, audit returns a result.
    fr = FakeResolver(unavailable=True)
    r = _audit(
        monkeypatch,
        boundary=ChemicalBoundary.EXECUTE,
        resolver=fr,
        field_id=None,
        season_id=None,
        diagnosis_ref=None,
        evidence_ref=None,
        human_approval=False,
    )
    assert not r.compliant
    assert r.mode == "audit"  # caller decides; audit itself never rejects
