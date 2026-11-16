"""W0-12 — VRA lab support comes only from the lab owner's results, never from the model.

``generate_vra_prescription`` is a tool the model calls; its parameters are written by
the model. Before W0-12 a ``lab_results`` list in those parameters was enough to mark a
zone ``lab_supported``, raise its confidence and lift the low-zone safety cap. Now the
only accepted source is the server-built ``evidence_context["approved_soil_lab"]`` block:
approved results with a ``result_id`` issued by the owner of ``soil_lab_results``
(sahool-platform, docs/architecture/db_ownership.yml).

Pure logic, plus the runtime fetcher path (fastapi-guarded) — Unit Tests job.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist.vra_prescription_engine import generate_vra_prescription  # noqa: E402

_FIELD = "field-1"


def _zones():
    return [
        {"zone_id": "pz-1", "productivity_class": "high", "area_ha": 4.0},
        {"zone_id": "pz-2", "productivity_class": "medium", "area_ha": 4.0},
        {"zone_id": "pz-3", "productivity_class": "low", "area_ha": 4.0},
    ]


def _owner_block(*records, owner="sahool-platform", field_id=_FIELD):
    block = {"owner": owner, "results": list(records)}
    if field_id is not None:
        block["field_id"] = field_id
    return {"approved_soil_lab": block}


def _approved(result_id="res-1", **values):
    return {"result_id": result_id, "quality_status": "approved", **(values or {"p": 12})}


def _levels(out):
    return {z["zone_id"]: z["evidence_level"] for z in out["prescription_zones"]}


_MODEL_LAB = [{"n": 30, "p": 12, "k": 180}]


# ── model-written lab results never grant lab support ───────────────────────
@pytest.mark.parametrize("key", ["lab_results", "soil_lab_results"])
def test_model_lab_results_do_not_make_any_zone_lab_supported(key):
    estimated = generate_vra_prescription(
        {"zones": _zones(), "allow_estimated": True}, field_id=_FIELD
    )
    out = generate_vra_prescription(
        {"zones": _zones(), "allow_estimated": True, key: _MODEL_LAB}, field_id=_FIELD
    )
    assert "lab_supported" not in set(_levels(out).values()), (
        f"model-written {key} must not mark a zone lab_supported: {_levels(out)}"
    )
    assert out["data_completeness"]["lab_results"] is False, (
        "model lab results must not count as lab completeness"
    )
    assert out["readiness_gate"]["reason"] == "estimated_with_user_consent", (
        f"unexpected gate reason: {out['readiness_gate']['reason']}"
    )
    assert out["readiness_gate"]["model_lab_results_ignored"] is True, (
        "the gate must say the model lab results were ignored"
    )
    assert out["readiness_gate"]["lab_evidence_source"] is None, (
        "no lab evidence source when no owner block exists"
    )
    assert [z["rate"] for z in out["prescription_zones"]] == [
        z["rate"] for z in estimated["prescription_zones"]
    ], "model lab results must not change the rates (low-zone cap stays)"
    assert out["vra_prescription"]["confidence"] == estimated["vra_prescription"]["confidence"], (
        "model lab results must not raise confidence"
    )
    assert any("معاملات الأداة" in w for w in out["warnings"]), (
        "the proposal must warn that tool-parameter lab results were ignored"
    )


def test_model_lab_results_without_consent_stay_blocked():
    out = generate_vra_prescription({"zones": _zones(), "lab_results": _MODEL_LAB}, field_id=_FIELD)
    assert out["vra_prescription"] is None, "no prescription from model lab results alone"
    assert out["readiness_gate"]["reason"] == "missing_lab_results_or_estimation_consent", (
        f"unexpected gate reason: {out['readiness_gate']['reason']}"
    )
    assert out["readiness_gate"]["model_lab_results_ignored"] is True, (
        "the blocked gate must say the model lab results were ignored"
    )


def test_model_zone_lineage_cannot_claim_lab_result_ids():
    zones = _zones()
    zones[0]["source_lineage"] = {"lab_result_ids": ["forged-1"], "zoning_run_id": "zr-1"}
    out = generate_vra_prescription(
        {"zones": zones, "allow_estimated": True, "lab_results": _MODEL_LAB}, field_id=_FIELD
    )
    lineage = out["prescription_zones"][0]["source_lineage"]
    assert "lab_result_ids" not in lineage, f"model-written lab ids must be dropped: {lineage}"
    assert lineage.get("zoning_run_id") == "zr-1", "other lineage keys are preserved"
    assert out["prescription_zones"][0]["evidence_level"] != "lab_supported", (
        "a zone's own lineage claim must not mark it lab_supported"
    )


# ── the owner's approved results are the one accepted source ────────────────
def test_owner_field_level_result_supports_every_zone_with_result_ids():
    out = generate_vra_prescription(
        {"zones": _zones()},
        field_id=_FIELD,
        evidence_context=_owner_block(_approved("res-1", p=12, k=180)),
    )
    assert set(_levels(out).values()) == {"lab_supported"}, f"levels: {_levels(out)}"
    assert out["readiness_gate"]["reason"] == "lab_supported", "all zones lab-backed"
    assert out["readiness_gate"]["lab_evidence_source"] == "approved_soil_lab", (
        "the gate must name the owner block as the lab source"
    )
    assert out["readiness_gate"]["model_lab_results_ignored"] is False, "nothing to ignore"
    for zone in out["prescription_zones"]:
        assert zone["source_lineage"].get("lab_result_ids") == ["res-1"], (
            f"zone lineage must carry the owner result id: {zone['source_lineage']}"
        )
    assert out["vra_prescription"]["source_lineage"].get("lab_result_ids") == ["res-1"], (
        "prescription lineage must carry the owner result ids"
    )


def test_owner_zone_result_supports_only_its_zone():
    out = generate_vra_prescription(
        {"zones": _zones(), "allow_estimated": True},
        field_id=_FIELD,
        evidence_context=_owner_block({**_approved("res-9"), "zone_id": "pz-3"}),
    )
    assert _levels(out) == {
        "pz-1": "estimated_requires_agronomist_review",
        "pz-2": "estimated_requires_agronomist_review",
        "pz-3": "lab_supported",
    }, f"levels: {_levels(out)}"
    assert out["prescription_zones"][2]["source_lineage"]["lab_result_ids"] == ["res-9"], (
        "the supported zone carries its result id"
    )
    assert "lab_result_ids" not in out["prescription_zones"][0]["source_lineage"], (
        "an unsupported zone carries no lab result id"
    )


@pytest.mark.parametrize(
    "context",
    [
        pytest.param(_owner_block({"quality_status": "approved", "p": 12}), id="no_result_id"),
        pytest.param(_owner_block({**_approved(), "result_id": "  "}), id="blank_result_id"),
        pytest.param(_owner_block({**_approved(), "quality_status": "pending"}), id="not_approved"),
        pytest.param(_owner_block({"result_id": "res-1", "p": 12}), id="no_quality_status"),
        pytest.param(_owner_block(_approved(), owner="ai_agronomist"), id="wrong_owner"),
        pytest.param({"approved_soil_lab": {"results": [_approved()]}}, id="no_owner"),
        pytest.param(_owner_block(_approved(), field_id="field-2"), id="other_field"),
        pytest.param(_owner_block({**_approved(), "p": "n/a"}), id="non_numeric_value"),
        pytest.param({"lab_results": [_approved()]}, id="other_context_key"),
    ],
)
def test_owner_block_fails_closed(context):
    out = generate_vra_prescription(
        {"zones": _zones(), "allow_estimated": True}, field_id=_FIELD, evidence_context=context
    )
    assert "lab_supported" not in set(_levels(out).values()), (
        f"invalid owner evidence must not grant lab support: {_levels(out)}"
    )
    assert out["data_completeness"]["lab_results"] is False, "invalid evidence is not lab data"


# ── runtime path: the pack, not the tool parameters, feeds the engine ───────
def _fetcher(pack):
    pytest.importorskip("fastapi")  # main imports fastapi
    from services.ai_agronomist import main as MAIN

    return MAIN._build_agent_tool_fetcher(
        field_state={"field_id": _FIELD}, ai_pack=pack, annotations={}
    )


def test_runtime_tool_ignores_model_lab_results_and_reads_the_pack():
    fetch = _fetcher({"field_id": _FIELD})
    out = fetch(
        "generate_vra_prescription",
        {"zones": _zones(), "allow_estimated": True, "lab_results": _MODEL_LAB},
    )
    assert "lab_supported" not in set(_levels(out).values()), (
        f"runtime: model lab results must not grant lab support: {_levels(out)}"
    )

    fetch = _fetcher({"field_id": _FIELD, **_owner_block(_approved("res-7"))})
    out = fetch("generate_vra_prescription", {"zones": _zones()})
    assert set(_levels(out).values()) == {"lab_supported"}, (
        f"runtime: the pack's owner block must grant lab support: {_levels(out)}"
    )
    assert out["vra_prescription"]["source_lineage"]["lab_result_ids"] == ["res-7"], (
        "runtime: lineage carries the owner result id"
    )
