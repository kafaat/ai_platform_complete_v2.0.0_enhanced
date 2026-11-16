"""W1-19 (scout-3): every diagnosis code resolves to an IPM plan through one registry.

Before: the symptom rules emitted ``wheat.rust`` / ``wheat.aphid`` / ``coffee.leaf_rust``,
the IPM advisor knew ``wheat_rust`` / ``aphid`` / ``fall_armyworm`` and a few Arabic names,
and the edge model said ``rust`` / ``armyworm`` / ``blight``. ``ipm_plan("wheat.rust")``
answered ``supported: False``, so no diagnosis ever became a plan.

Now ``shared/agronomy/pest_taxonomy.py`` is the one vocabulary. These cases measure:

* every pest/disease code the rule engine can emit opens a real IPM ladder;
* every nutrient/water/salinity code gets a named referral, never an IPM ladder;
* every label in the edge model's label manifest resolves to the code the manifest names,
  and that code has a plan;
* the registry and the advisor's plans cannot drift apart silently;
* ``POST /api/v1/diagnose`` (``DiagnosisResult.to_dict``) carries ``ipm_plan_ref``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.agronomy import pest_taxonomy

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LABEL_MANIFEST = ROOT / "services" / "edge-inference" / "models_manifest" / "pest_labels.json"


@pytest.fixture(scope="module")
def ipm():
    from api import ipm_advisor

    return ipm_advisor


@pytest.fixture(scope="module")
def dx():
    from api import disease_diagnosis

    return disease_diagnosis


def test_every_pest_or_disease_diagnosis_code_opens_an_ipm_plan(ipm, dx):
    biotic = [r for r in dx.SYMPTOM_RULES if r.category in ("pest", "disease")]
    assert biotic, "the rule engine has no pest/disease rules to measure"
    for rule in biotic:
        plan = ipm.ipm_plan(rule.issue_code)
        assert plan["supported"] is True, f"{rule.issue_code} does not resolve to an IPM plan"
        assert len(plan["ipm_ladder"]) == 4, f"{rule.issue_code}: IPM ladder is not 4 stages"
        assert plan["taxonomy_code"] == pest_taxonomy.resolve_code(rule.issue_code), (
            f"{rule.issue_code}: plan opened for a different code than the registry names"
        )


def test_every_diagnosis_code_is_in_the_registry(dx):
    for rule in dx.SYMPTOM_RULES:
        entry = pest_taxonomy.resolve(rule.issue_code)
        assert entry is not None, f"diagnosis code {rule.issue_code} is not in the registry"
        assert entry.category == rule.category, (
            f"{rule.issue_code}: registry category {entry.category} != rule {rule.category}"
        )


def test_non_biotic_codes_get_a_referral_and_never_an_ipm_ladder(ipm, dx):
    non_biotic = [r for r in dx.SYMPTOM_RULES if r.category not in ("pest", "disease")]
    assert non_biotic, "the rule engine has no non-biotic rules to measure"
    for rule in non_biotic:
        plan = ipm.ipm_plan(rule.issue_code)
        assert plan["supported"] is False, f"{rule.issue_code} got an IPM ladder"
        assert plan["ipm_status"] == "not_applicable", f"{rule.issue_code}: {plan}"
        assert plan["referral"], f"{rule.issue_code}: no referral named"
        assert plan["ipm_plan_ref"] is None, f"{rule.issue_code}: carries a plan ref"


def test_registry_and_plans_cannot_drift(ipm):
    biotic = {e.code for e in pest_taxonomy.entries() if e.ipm_applicable}
    planned = set(ipm._PESTS)
    assert biotic - planned == set(), f"registry codes with no authored plan: {biotic - planned}"
    assert planned - biotic == set(), f"plans keyed by a non-registry code: {planned - biotic}"


def test_a_missing_plan_fails_closed_with_a_named_status(ipm, monkeypatch):
    trimmed = {k: v for k, v in ipm._PESTS.items() if k != "late_blight"}
    monkeypatch.setattr(ipm, "_PESTS", trimmed)
    plan = ipm.ipm_plan("blight")
    assert plan["supported"] is False, "another organism's plan was served for a missing one"
    assert plan["ipm_status"] == "plan_missing", f"drift not named: {plan}"
    assert plan["ipm_plan_ref"] is None, "a ref to an absent plan was returned"


def test_every_edge_manifest_label_resolves_to_its_declared_code_and_a_plan(ipm):
    manifest = json.loads(LABEL_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["labels"], "label manifest is empty"
    for entry in manifest["labels"]:
        label, code = entry["label"], entry["taxonomy_code"]
        assert pest_taxonomy.get(code) is not None, f"{label}: {code} is not a canonical code"
        assert pest_taxonomy.resolve_code(label) == code, (
            f"edge label {label} resolves to {pest_taxonomy.resolve_code(label)}, manifest says {code}"
        )
        assert ipm.ipm_plan(label)["supported"] is True, f"edge label {label} has no IPM plan"


def test_legacy_spellings_still_resolve(ipm):
    for spelling, code in (
        ("fall_armyworm", "fall_armyworm"),
        ("دودة الحشد", "fall_armyworm"),
        ("صدأ", "wheat_rust"),
        ("rust", "wheat_rust"),
        ("المنّ", "aphid"),
        ("  Wheat.Rust ", "wheat_rust"),
    ):
        plan = ipm.ipm_plan(spelling)
        assert plan["supported"] is True and plan["pest"] == code, f"{spelling!r}: {plan}"


def test_an_unknown_code_is_named_not_silent(ipm):
    plan = ipm.ipm_plan("not.a.real.code")
    assert plan["supported"] is False, "an unknown code got a plan"
    assert plan["ipm_status"] == "code_not_in_taxonomy", f"unknown code not named: {plan}"
    assert plan["taxonomy_code"] is None, "an unknown code was given a taxonomy code"


def test_an_alias_cannot_map_to_two_codes(monkeypatch):
    dup = (
        pest_taxonomy.TaxonEntry("a", "pest", "أ", None, aliases=("x",)),
        pest_taxonomy.TaxonEntry("b", "pest", "ب", None, aliases=("X ",)),
    )
    monkeypatch.setattr(pest_taxonomy, "_ENTRIES", dup)
    with pytest.raises(ValueError, match="two codes"):
        pest_taxonomy._build_index()


def test_diagnose_returns_ipm_plan_ref_for_a_disease(dx):
    body = dx.diagnose("wheat", ["orange_pustules", "leaf_yellowing"]).to_dict()
    top = body["candidates"][0]
    assert top["issue_code"] == "wheat.rust", f"unexpected top candidate: {top}"
    expected = {"code": "wheat_rust", "path": "/api/v1/ipm/plan?pest=wheat_rust"}
    assert top["ipm_plan_ref"] == expected, f"candidate ref: {top}"
    assert top["taxonomy_code"] == "wheat_rust", f"candidate code: {top}"
    assert body["ipm_plan_ref"] == expected, f"top-level ref: {body.get('ipm_plan_ref')}"


def test_diagnose_returns_a_referral_not_a_plan_for_a_deficiency(dx):
    body = dx.diagnose("wheat", ["general_yellowing", "old_leaves_affected"]).to_dict()
    top = body["candidates"][0]
    assert top["issue_code"] == "wheat.n_deficiency", f"unexpected top candidate: {top}"
    assert top["ipm_plan_ref"] is None, "a nutrient deficiency was pointed at an IPM plan"
    assert top["ipm_status"] == "not_applicable", f"{top}"
    assert top["referral"] == "soil_or_tissue_lab_test", f"{top}"
    assert body["ipm_plan_ref"] is None, "top-level ref set for a deficiency"


def test_no_candidate_means_no_ref(dx):
    body = dx.diagnose("wheat", []).to_dict()
    assert body["candidates"] == [], f"unexpected candidates: {body['candidates']}"
    assert body["ipm_plan_ref"] is None, "a ref without a candidate"
