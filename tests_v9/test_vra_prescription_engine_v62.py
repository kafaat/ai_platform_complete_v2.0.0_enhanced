"""V62 VRA Prescription Engine guards."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import tool_executor as EX  # noqa: E402
from services.ai_agronomist.vra_prescription_engine import generate_vra_prescription  # noqa: E402
from shared.ai import tool_schema as SCH  # noqa: E402


def _zones():
    return [
        {
            "zone_id": "pz-1",
            "productivity_class": "high",
            "area_ha": 4.0,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[44.18, 16.16], [44.19, 16.16], [44.19, 16.18], [44.18, 16.18], [44.18, 16.16]]
                ],
            },
        },
        {
            "zone_id": "pz-2",
            "productivity_class": "medium",
            "area_ha": 4.0,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[44.19, 16.16], [44.20, 16.16], [44.20, 16.18], [44.19, 16.18], [44.19, 16.16]]
                ],
            },
        },
        {
            "zone_id": "pz-3",
            "productivity_class": "low",
            "area_ha": 4.0,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[44.20, 16.16], [44.21, 16.16], [44.21, 16.18], [44.20, 16.18], [44.20, 16.16]]
                ],
            },
        },
    ]


def test_vra_prescription_blocks_without_zones():
    out = generate_vra_prescription({"product_type": "fertilizer", "allow_estimated": True})
    assert out["vra_prescription"] is None
    assert out["readiness_gate"]["status"] == "blocked"
    assert out["readiness_gate"]["reason"] == "missing_productivity_zones"
    assert out["ready_for_machine_export"] is False


def test_vra_prescription_requires_lab_or_estimation_consent():
    out = generate_vra_prescription({"zones": _zones(), "product_type": "fertilizer"})
    assert out["vra_prescription"] is None
    assert out["readiness_gate"]["reason"] == "missing_lab_results_or_estimation_consent"


def test_vra_prescription_proposes_zone_rates_with_estimation_warning():
    out = generate_vra_prescription(
        {
            "zones": _zones(),
            "product_type": "fertilizer",
            "crop": "wheat",
            "base_rate": 100,
            "allow_estimated": True,
        },
        field_id="field-1",
    )
    assert out["requires_user_confirmation"] is True
    assert out["persistence"] == "proposal_only_until_user_confirms"
    assert out["ready_for_machine_export"] is False
    assert out["vra_prescription"]["product_type"] == "fertilizer"
    rates = [z["rate"] for z in out["prescription_zones"]]
    assert rates[0] == 100
    assert rates[1] < rates[0]
    assert rates[2] > rates[0]
    assert out["warnings"]


def test_vra_prescription_lab_supported_has_higher_confidence():
    estimated = generate_vra_prescription({"zones": _zones(), "allow_estimated": True})
    lab = generate_vra_prescription(
        {"zones": _zones(), "lab_results": [{"zone_id": "pz-1", "p": 12}]}
    )
    assert lab["vra_prescription"]["confidence"] > estimated["vra_prescription"]["confidence"]
    assert lab["readiness_gate"]["status"] == "review_required_before_export"


def test_vra_tools_are_proposal_then_approval_write():
    proposal = EX.plan_tool_call(
        "generate_vra_prescription",
        {"zones": _zones(), "allow_estimated": True},
        ["can_read_historical_imagery"],
    )
    assert proposal["outcome"] == "allowed"
    assert proposal["risk"] == "low"

    create = EX.plan_tool_call(
        "create_prescription_map",
        {"field_id": "f", "prescription_id": "vra-proposal-1", "product_type": "fertilizer"},
        ["can_generate_prescriptions"],
    )
    assert create["outcome"] == "pending_approval"
    assert create["risk"] == "high"
    assert create["requires_approval"] is True


def test_provider_schema_exposes_vra_inputs():
    defs = SCH.tool_definitions(["can_read_historical_imagery"])
    tool = next(d for d in defs if d["name"] == "generate_vra_prescription")
    props = tool["parameters"]["properties"]
    assert props["zones"]["type"] == "array"
    assert props["soil_sampling_plan"]["type"] == "object"
    assert props["lab_results"]["type"] == "array"
    assert props["product_type"]["enum"] == ["fertilizer", "lime", "seed", "irrigation"]


# ── units: one canonical unit per product ───────────────────────────────────
def test_vra_rejects_unit_that_differs_from_product_unit():
    out = generate_vra_prescription(
        {"zones": _zones(), "product_type": "lime", "unit": "kg_ha", "allow_estimated": True}
    )
    assert out["vra_prescription"] is None
    assert out["prescription_zones"] == []
    assert out["readiness_gate"]["status"] == "blocked"
    assert out["readiness_gate"]["reason"] == "unit_mismatch_for_product"
    assert out["readiness_gate"]["expected_unit"] == "t_ha"


def test_vra_accepts_the_product_unit_and_its_spelling_variants():
    for unit in (None, "t_ha", "t/ha", " T_HA "):
        params = {"zones": _zones(), "product_type": "lime", "allow_estimated": True}
        if unit is not None:
            params["unit"] = unit
        out = generate_vra_prescription(params)
        assert out["vra_prescription"]["unit"] == "t_ha"
        assert {z["unit"] for z in out["prescription_zones"]} == {"t_ha"}


# ── no invented productivity class ──────────────────────────────────────────
def test_vra_blocks_zone_without_productivity_class():
    zones = _zones()
    del zones[1]["productivity_class"]
    out = generate_vra_prescription({"zones": zones, "allow_estimated": True})
    assert out["vra_prescription"] is None
    assert out["prescription_zones"] == []
    assert out["readiness_gate"]["status"] == "blocked"
    assert out["readiness_gate"]["reason"] == "unclassified_productivity_zones"
    assert out["readiness_gate"]["unclassified_zone_ids"] == ["pz-2"]


# ── lab evidence must be structured analyte data ────────────────────────────
def test_vra_unstructured_lab_results_are_not_lab_evidence():
    blocked = generate_vra_prescription({"zones": _zones(), "lab_results": ["n/a"]})
    assert blocked["vra_prescription"] is None
    assert blocked["readiness_gate"]["reason"] == "missing_lab_results_or_estimation_consent"

    estimated = generate_vra_prescription({"zones": _zones(), "allow_estimated": True})
    junk = generate_vra_prescription(
        {"zones": _zones(), "lab_results": ["n/a", {"note": "pending"}], "allow_estimated": True}
    )
    assert junk["data_completeness"]["lab_results"] is False
    assert {z["evidence_level"] for z in junk["prescription_zones"]} == {
        "estimated_requires_agronomist_review"
    }
    assert junk["vra_prescription"]["confidence"] == estimated["vra_prescription"]["confidence"]
    assert [z["rate"] for z in junk["prescription_zones"]] == [
        z["rate"] for z in estimated["prescription_zones"]
    ]


def test_vra_zone_lab_record_supports_only_its_own_zone():
    out = generate_vra_prescription(
        {"zones": _zones(), "lab_results": [{"zone_id": "pz-1", "p": 12}], "allow_estimated": True}
    )
    levels = {z["zone_id"]: z["evidence_level"] for z in out["prescription_zones"]}
    assert levels == {
        "pz-1": "lab_supported",
        "pz-2": "estimated_requires_agronomist_review",
        "pz-3": "estimated_requires_agronomist_review",
    }
    # The low zone has no lab record of its own, so its estimated cap still applies.
    estimated = generate_vra_prescription({"zones": _zones(), "allow_estimated": True})
    assert out["prescription_zones"][2]["rate"] == estimated["prescription_zones"][2]["rate"]
    assert out["readiness_gate"]["reason"] == "partial_lab_support"


def test_vra_zone_area_uses_polygon_not_bbox():
    from services.ai_agronomist.field_boundary_ai import area_ha_for_bbox

    triangle = {
        "type": "Polygon",
        "coordinates": [[[44.18, 16.16], [44.19, 16.16], [44.18, 16.17], [44.18, 16.16]]],
    }
    bbox_area = area_ha_for_bbox([44.18, 16.16, 44.19, 16.17])
    out = generate_vra_prescription(
        {
            "zones": [{"zone_id": "tri", "productivity_class": "high", "geometry": triangle}],
            "allow_estimated": True,
        }
    )
    area = out["prescription_zones"][0]["area_ha"]
    assert abs(area - bbox_area / 2) < 0.5, (area, bbox_area)
    assert out["vra_prescription"]["total_area_ha"] == area
