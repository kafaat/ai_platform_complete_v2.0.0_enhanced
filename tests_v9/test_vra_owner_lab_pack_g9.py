"""G9 (F-E10) — the VRA prescription is fed the lab owner's approved result, or says it had none.

The platform builds the advisor's ``approved_soil_lab`` block from the lab owner's read
(``lab_store.latest_soil_4r_rows``, the field 4R plan's read) with
``lab_store.approved_soil_lab_block``; the VRA engine uses only approved records of that
block for the same field and tenant, and reports what it used (method, unit, sampling
date, approval reference) or that it computed without laboratory data. Pure functions;
the DB read itself is proved in ``test_vra_owner_lab_pack_g9_live_pg.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist.vra_prescription_engine import (  # noqa: E402
    _LAB_ANALYTES,
    generate_vra_prescription,
)


def _load_lab_store():
    path = ROOT / "services" / "sahool-platform" / "api" / "lab_store.py"
    spec = importlib.util.spec_from_file_location("g9_platform_lab_store", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LAB_STORE = _load_lab_store()
_FIELD, _TENANT = "field-1", "00000000-0000-0000-0000-00000000000a"
_ZONES = [
    {"zone_id": "pz-1", "productivity_class": "high", "area_ha": 4.0},
    {"zone_id": "pz-2", "productivity_class": "low", "area_ha": 4.0},
]


def _row(analyte="phosphorus_mg_kg", value="12.0", **over):
    row = {
        "sample_id": "s-1",
        "sampled_on": date(2026, 11, 1),
        "zone_id": None,
        "analyte": analyte,
        "result_id": f"r-{analyte}",
        "unit": "mg/kg",
        "value_json": value,  # asyncpg returns JSONB as text
        "method_code": "olsen",
        "quality_status": "approved",
        "approved_at": datetime(2026, 11, 3, 8, 0, tzinfo=UTC),
    }
    row.update(over)
    return row


def _ctx(block, tenant=_TENANT):
    return {"tenant_id": tenant, "approved_soil_lab": block}


def _levels(out):
    return {z["evidence_level"] for z in out["prescription_zones"]}


# ── platform side: the owner block ──────────────────────────────────────────
def test_block_passes_the_approved_result_with_method_unit_date_and_approval_ref():
    block = LAB_STORE.approved_soil_lab_block(
        _FIELD, _TENANT, [_row(), _row("ph", "7.9", unit="1", method_code="saturated_paste")]
    )
    assert block["owner"] == "sahool-platform" and block["status"] == "available"
    assert block["field_id"] == _FIELD and block["tenant_id"] == _TENANT
    p = {r["analyte"]: r for r in block["results"]}["phosphorus_mg_kg"]
    assert p == {
        "result_id": "r-phosphorus_mg_kg",
        "analyte": "phosphorus_mg_kg",
        "value": 12.0,
        "unit": "mg/kg",
        "method_code": "olsen",
        "quality_status": "approved",
        "sample_id": "s-1",
        "sampled_on": "2026-11-01",
        "approved_at": "2026-11-03T08:00:00+00:00",
        "approval_ref": "soil_lab_results:r-phosphorus_mg_kg",
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"quality_status": "unreviewed"},
        {"quality_status": "rejected"},
        {"quality_status": None},
        {"result_id": None},
        {"value_json": "null"},
    ],
)
def test_block_leaves_out_rows_that_are_not_approved_owner_results(bad):
    block = LAB_STORE.approved_soil_lab_block(_FIELD, _TENANT, [_row(**bad)])
    assert block["results"] == [], block
    assert block["status"] == "unavailable"
    assert block["reason"] == "no_approved_soil_lab_result"


def test_no_rows_give_an_explicit_unavailable_block():
    block = LAB_STORE.approved_soil_lab_block(_FIELD, _TENANT, [])
    assert block["status"] == "unavailable" and block["results"] == []


def test_engine_recognises_every_numeric_analyte_the_lab_owner_stores():
    payload = SimpleNamespace(
        ph=1.0,
        ec_dsm=1.0,
        organic_matter_pct=1.0,
        nitrogen_mg_kg=1.0,
        phosphorus_mg_kg=1.0,
        potassium_mg_kg=1.0,
        cec_cmol_kg=1.0,
        calcium_carbonate_pct=1.0,
        sand_pct=1.0,
        silt_pct=1.0,
        clay_pct=1.0,
        texture=None,
        ec_extraction_method=None,
        method_code="m",
        detection_limit=None,
        uncertainty=None,
        supersedes_result_ids={},
    )
    owner_names = {row["analyte"] for row in LAB_STORE.soil_result_analytes(payload)}
    assert owner_names - _LAB_ANALYTES == set(), (
        "an approved owner result would be dropped as an unknown analyte"
    )


# ── engine side: what reaches the prescription ──────────────────────────────
def test_approved_owner_block_reaches_the_prescription_with_its_provenance():
    block = LAB_STORE.approved_soil_lab_block(_FIELD, _TENANT, [_row()])
    out = generate_vra_prescription(
        {"zones": _ZONES}, field_id=_FIELD, evidence_context=_ctx(block)
    )
    assert _levels(out) == {"lab_supported"}
    basis = out["vra_prescription"]["laboratory_basis"]
    assert basis["status"] == "approved_laboratory_results"
    (used,) = basis["results"]
    assert used["method_code"] == "olsen" and used["unit"] == "mg/kg"
    assert used["sampled_on"] == "2026-11-01"
    assert used["approval_ref"] == "soil_lab_results:r-phosphorus_mg_kg"
    assert out["readiness_gate"]["laboratory_basis"] == "approved_laboratory_results"


def test_no_owner_lab_states_computed_without_laboratory_data():
    block = LAB_STORE.approved_soil_lab_block(_FIELD, _TENANT, [])
    out = generate_vra_prescription(
        {"zones": _ZONES, "allow_estimated": True}, field_id=_FIELD, evidence_context=_ctx(block)
    )
    basis = out["vra_prescription"]["laboratory_basis"]
    assert basis["status"] == "computed_without_laboratory_data"
    assert basis["results"] == [] and basis["statement_ar"]
    assert out["readiness_gate"]["laboratory_basis"] == "computed_without_laboratory_data"
    assert "lab_supported" not in _levels(out)


def test_unapproved_record_in_the_block_is_not_used():
    block = LAB_STORE.approved_soil_lab_block(_FIELD, _TENANT, [_row()])
    block["results"][0]["quality_status"] = "unreviewed"
    out = generate_vra_prescription(
        {"zones": _ZONES, "allow_estimated": True}, field_id=_FIELD, evidence_context=_ctx(block)
    )
    assert "lab_supported" not in _levels(out)
    assert out["vra_prescription"]["laboratory_basis"]["status"] == (
        "computed_without_laboratory_data"
    )


@pytest.mark.parametrize("context_tenant", ["00000000-0000-0000-0000-00000000000b", None])
def test_block_for_another_tenant_is_not_used(context_tenant):
    block = LAB_STORE.approved_soil_lab_block(_FIELD, _TENANT, [_row()])
    out = generate_vra_prescription(
        {"zones": _ZONES, "allow_estimated": True},
        field_id=_FIELD,
        evidence_context=_ctx(block, tenant=context_tenant),
    )
    assert "lab_supported" not in _levels(out)
    assert out["readiness_gate"]["lab_evidence_source"] is None
    assert out["vra_prescription"]["laboratory_basis"]["results"] == []


def test_runtime_fetcher_checks_the_block_against_the_pack_tenant():
    pytest.importorskip("fastapi")  # the runtime module imports fastapi
    from services.ai_agronomist import ai_evidence_runtime as runtime

    block = LAB_STORE.approved_soil_lab_block(_FIELD, _TENANT, [_row()])
    for pack_tenant, expected in ((_TENANT, {"lab_supported"}), ("other-tenant", None)):
        pack = {"field_id": _FIELD, "tenant_id": pack_tenant, "approved_soil_lab": block}
        fetch = runtime._build_agent_tool_fetcher(
            field_state={"field_id": _FIELD}, ai_pack=pack, annotations={}
        )
        out = fetch("generate_vra_prescription", {"zones": _ZONES, "allow_estimated": True})
        if expected:
            assert _levels(out) == expected
        else:
            assert "lab_supported" not in _levels(out)


@pytest.mark.parametrize("rows", [[], [_row()]])
def test_prescription_stays_review_required_and_not_machine_exportable(rows):
    block = LAB_STORE.approved_soil_lab_block(_FIELD, _TENANT, rows)
    out = generate_vra_prescription(
        {"zones": _ZONES, "allow_estimated": True}, field_id=_FIELD, evidence_context=_ctx(block)
    )
    assert out["ready_for_machine_export"] is False
    assert out["readiness_gate"]["ready_for_machine_export"] is False
    assert out["vra_prescription"]["requires_agronomist_review"] is True
    assert {"human_approval", "agronomist_review"} <= set(
        out["readiness_gate"]["required_before_export"]
    )
