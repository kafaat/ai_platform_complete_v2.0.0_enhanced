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
